from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db import get_conn
from src.models.criteria import CriteriaSchema
from src.models.envelop import Envelope, FinanceInput
from src.services import session_store as store
from src.services.discover import ask_next_question, discover
from src.services.explain import explain
from src.services.finance import Finance, to_envelope
from src.services.retrieval import retrieve

router = APIRouter(prefix="/api/v1")

TOP_K = 5


# ---------- schemas ----------

class MessageIn(BaseModel):
    text: str


class MessageOut(BaseModel):
    reply: str
    criteria: CriteriaSchema
    completeness: float


class ReorderIn(BaseModel):
    unit_id: str
    new_rank: int
    reason: str


class RemoveIn(BaseModel):
    reason: str


class FeedbackIn(BaseModel):
    unit_id: str
    intent: str  # 'want_visit' | 'rejected'
    reason_tag: str | None = None  # required if intent == 'rejected'
    note: str | None = None


# ---------- helpers ----------

def _generate_shortlist(conn, session_id: str) -> None:
    row = store.get_session(conn, session_id)
    criteria = store.load_criteria(row)
    envelope = store.load_envelope(row)
    if criteria is None or envelope is None:
        return
    scored = retrieve(criteria, envelope, conn)
    top = scored[:TOP_K]
    ranked = [(s, *explain(s, criteria, envelope)) for s in top]
    store.save_shortlist(conn, session_id, ranked)


def _require_session(conn, session_id: str):
    row = store.get_session(conn, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return row


# ---------- customer endpoints ----------

@router.post("/sessions")
async def create_session():
    conn = get_conn()
    session_id = store.create_session(conn)
    conn.close()
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
async def post_message(session_id: str, body: MessageIn):
    conn = get_conn()
    row = _require_session(conn, session_id)

    store.add_message(conn, session_id, "customer", body.text)

    existing = store.load_criteria(row)
    pois = conn.execute("SELECT * FROM poi").fetchall()
    result = discover(body.text, pois)
    store.add_llm_usage(conn, session_id, result.llm_usage)

    if existing is not None:
        merged = existing.model_copy(deep=True)
        for field, value in result.criteria.hard_constraints.model_dump().items():
            if value is not None:
                setattr(merged.hard_constraints, field, value)
        existing_keys = {p.key for p in merged.soft_preferences}
        for pref in result.criteria.soft_preferences:
            if pref.key not in existing_keys:
                merged.soft_preferences.append(pref)
        merged.completeness = max(merged.completeness, result.criteria.completeness)
        criteria = merged
    else:
        criteria = result.criteria

    next_q = ask_next_question(result)
    if next_q:
        reply = next_q
    elif result.cash_available_vnd is not None and result.income_monthly_vnd is not None:
        # Khách đã cho đủ vốn tự có + thu nhập trong chính câu này — tính luôn, không hỏi lại
        # (schemas.md: không lưu thu nhập/tiết kiệm thô, chỉ lưu bucket + envelope đã dẫn xuất).
        fin = Finance(
            savings=result.cash_available_vnd, monthly_income=result.income_monthly_vnd,
            monthly_debt=result.existing_debt_monthly_vnd,
        )
        envelope = to_envelope(fin)
        store.save_envelope(conn, session_id, envelope)
        criteria.hard_constraints.price_max_vnd = envelope.price_max_vnd
        _generate_shortlist(conn, session_id)
        reply = (
            f"Mình đã hiểu nhu cầu của bạn. Với thông tin tài chính bạn vừa cho, tầm giá phù hợp là "
            f"{envelope.price_min_vnd / 1e9:.2f} – {envelope.price_max_vnd / 1e9:.2f} tỷ "
            f"(trả góp {envelope.installment_promo_vnd / 1e6:.1f}tr → "
            f"{envelope.installment_float_vnd / 1e6:.1f}tr/tháng). Xem chi tiết ở trang Tài chính, "
            f"hoặc đợi sale duyệt để nhận shortlist."
        )
    else:
        reply = (
            "Mình đã hiểu nhu cầu của bạn. Tiếp theo, hãy cho mình biết vốn tự có, thu nhập "
            "và khoản nợ hàng tháng (nếu có) để tính khả năng tài chính."
        )

    store.save_criteria(conn, session_id, criteria)
    store.add_message(conn, session_id, "agent", reply)
    conn.close()
    return MessageOut(reply=reply, criteria=criteria, completeness=criteria.completeness)


@router.post("/sessions/{session_id}/finance", response_model=Envelope)
async def post_finance(session_id: str, body: FinanceInput):
    conn = get_conn()
    row = _require_session(conn, session_id)

    fin = Finance(
        savings=body.cash_available_vnd, monthly_income=body.income_monthly_vnd,
        monthly_debt=body.existing_debt_monthly_vnd, term_years=body.loan_term_years,
    )
    envelope = to_envelope(fin)
    store.save_envelope(conn, session_id, envelope)

    criteria = store.load_criteria(row) or CriteriaSchema()
    criteria.hard_constraints.price_max_vnd = envelope.price_max_vnd
    store.save_criteria(conn, session_id, criteria)

    _generate_shortlist(conn, session_id)
    conn.close()
    return envelope


@router.post("/sessions/{session_id}/scenarios")
async def post_scenarios(session_id: str):
    conn = get_conn()
    row = _require_session(conn, session_id)
    envelope = store.load_envelope(row)
    conn.close()
    if envelope is None:
        raise HTTPException(status_code=400, detail="finance chưa được tính cho phiên này")
    return {"scenarios": envelope.scenarios}


@router.get("/sessions/{session_id}/shortlist")
async def get_shortlist(session_id: str):
    conn = get_conn()
    row = _require_session(conn, session_id)

    if row["state"] != "sent":
        envelope = store.load_envelope(row)
        conn.close()
        return {
            "state": row["state"],
            "price_min_vnd": envelope.price_min_vnd if envelope else None,
            "price_max_vnd": envelope.price_max_vnd if envelope else None,
        }

    units = store.load_shortlist(conn, session_id)
    conn.close()
    return {"state": "sent", "units": units}


@router.post("/sessions/{session_id}/feedback")
async def post_feedback(session_id: str, body: FeedbackIn):
    conn = get_conn()
    _require_session(conn, session_id)
    if body.intent == "rejected" and not body.reason_tag:
        conn.close()
        raise HTTPException(status_code=422, detail="reason_tag is required when intent='rejected'")
    store.add_feedback(conn, session_id, body.unit_id, body.intent, body.reason_tag, body.note)
    conn.close()
    return {"ok": True}


# ---------- sale (HITL) endpoints ----------

@router.get("/queue")
async def get_queue():
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, criteria, envelope, created_at FROM session "
        "WHERE state = 'awaiting_review' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        envelope = store.load_envelope(row)
        out.append({
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "price_min_vnd": envelope.price_min_vnd if envelope else None,
            "price_max_vnd": envelope.price_max_vnd if envelope else None,
        })
    return {"queue": out}


@router.get("/sessions/{session_id}/review")
async def get_review(session_id: str):
    conn = get_conn()
    row = _require_session(conn, session_id)
    criteria = store.load_criteria(row)
    envelope = store.load_envelope(row)
    units = store.load_shortlist_internal(conn, session_id)
    conn.close()
    return {
        "session_id": session_id, "state": row["state"],
        "criteria": criteria, "envelope": envelope, "units": units,
    }


@router.patch("/sessions/{session_id}/criteria")
async def patch_criteria(session_id: str, criteria: CriteriaSchema):
    conn = get_conn()
    row = _require_session(conn, session_id)
    envelope = store.load_envelope(row)
    if envelope is None:
        conn.close()
        raise HTTPException(status_code=400, detail="finance chưa được tính cho phiên này")
    criteria.hard_constraints.price_max_vnd = envelope.price_max_vnd
    store.save_criteria(conn, session_id, criteria)
    _generate_shortlist(conn, session_id)
    store.audit(conn, session_id, actor_id=store.DEMO_SALE_USER_ID, action="update_criteria")
    conn.close()
    return {"ok": True}


@router.post("/sessions/{session_id}/units/{unit_id}/remove")
async def remove_shortlist_unit(session_id: str, unit_id: str, body: RemoveIn):
    conn = get_conn()
    _require_session(conn, session_id)
    store.remove_unit(conn, session_id, unit_id, body.reason)
    conn.close()
    return {"ok": True}


@router.post("/sessions/{session_id}/reorder")
async def reorder_units(session_id: str, body: ReorderIn):
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required to reorder")
    conn = get_conn()
    _require_session(conn, session_id)
    store.reorder(conn, session_id, body.unit_id, body.new_rank, body.reason)
    conn.close()
    return {"ok": True}


@router.post("/sessions/{session_id}/approve")
async def approve_session(session_id: str):
    conn = get_conn()
    _require_session(conn, session_id)
    store.approve(conn, session_id)
    conn.close()
    return {"ok": True}


@router.get("/audit")
async def get_audit(session_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE session_id = ? ORDER BY created_at ASC", (session_id,)
    ).fetchall()
    conn.close()
    return {"entries": [dict(r) for r in rows]}

"""Quản lý session trong SQLite theo docs/schemas.md: tạo phiên (kèm app_user khách),
lưu/đọc criteria + envelope, lưu shortlist, audit log, llm_usage. Một hàm mỏng bọc SQL,
không có business logic (đó là việc của discover / finance / retrieval / explain)."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from src.models.criteria import CriteriaSchema
from src.models.envelop import Envelope
from src.models.shortlist import RankedUnit, RankedUnitInternal, UnitFacts
from src.services.discover import LlmUsage
from src.services.retrieval import ScoredUnit

DEMO_SALE_USER_ID = 1  # seed.py tạo sẵn 1 app_user role='sale' với id này


def now() -> str:
    return datetime.now(UTC).isoformat()


def create_session(conn: sqlite3.Connection) -> str:
    ts = now()
    cur = conn.execute(
        "INSERT INTO app_user (role, display_name, phone_masked, created_at) VALUES ('customer', 'Khách', NULL, ?)",
        (ts,),
    )
    customer_id = cur.lastrowid

    session_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO session
           (session_id, customer_id, assigned_sale_id, state, completeness, created_at, updated_at)
           VALUES (?, ?, ?, 'draft', 0, ?, ?)""",
        (session_id, customer_id, DEMO_SALE_USER_ID, ts, ts),
    )
    conn.commit()
    return session_id


def get_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM session WHERE session_id = ?", (session_id,)).fetchone()


def add_message(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO message (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now()),
    )
    conn.commit()


def save_criteria(conn: sqlite3.Connection, session_id: str, criteria: CriteriaSchema) -> None:
    conn.execute(
        "UPDATE session SET criteria = ?, completeness = ?, updated_at = ? WHERE session_id = ?",
        (criteria.model_dump_json(), criteria.completeness, now(), session_id),
    )
    conn.commit()


def load_criteria(row: sqlite3.Row) -> CriteriaSchema | None:
    if not row["criteria"]:
        return None
    return CriteriaSchema.model_validate_json(row["criteria"])


def save_envelope(conn: sqlite3.Connection, session_id: str, envelope: Envelope) -> None:
    conn.execute(
        "UPDATE session SET envelope = ?, income_bucket = ?, state = 'awaiting_review', updated_at = ? "
        "WHERE session_id = ?",
        (envelope.model_dump_json(), envelope.income_bucket, now(), session_id),
    )
    conn.commit()


def load_envelope(row: sqlite3.Row) -> Envelope | None:
    if not row["envelope"]:
        return None
    return Envelope.model_validate_json(row["envelope"])


def add_llm_usage(conn: sqlite3.Connection, session_id: str, usage: LlmUsage) -> None:
    conn.execute(
        """INSERT INTO llm_usage (session_id, node, model, tokens_in, tokens_out, cost_usd, latency_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, usage.node, usage.model, usage.tokens_in, usage.tokens_out,
         usage.cost_usd, usage.latency_ms, now()),
    )
    conn.commit()


def _unit_facts(row: sqlite3.Row) -> UnitFacts:
    return UnitFacts(
        unit_id=row["unit_id"], project_name=row["project_name"], district=row["district"],
        bedrooms=row["bedrooms"], bathrooms=row["bathrooms"], area_sqm=row["area_sqm"],
        floor=row["floor"], total_floors=row["total_floors"], balcony_dir=row["balcony_dir"],
        view_type=row["view_type"], price_vnd=row["price_vnd"], handover_date=row["handover_date"],
    )


def save_shortlist(
    conn: sqlite3.Connection, session_id: str, ranked: list[tuple[ScoredUnit, list[str], list[str]]],
) -> None:
    conn.execute("DELETE FROM shortlist_item WHERE session_id = ?", (session_id,))
    for rank, (scored, reasons, tradeoffs) in enumerate(ranked, start=1):
        conn.execute(
            """INSERT INTO shortlist_item
               (session_id, unit_id, rank, match_score, reasons, tradeoffs, origin, is_removed, over_envelope)
               VALUES (?, ?, ?, ?, ?, ?, 'system', 0, 0)""",
            (session_id, scored.row["unit_id"], rank, scored.match_score,
             json.dumps(reasons, ensure_ascii=False), json.dumps(tradeoffs, ensure_ascii=False)),
        )
    conn.commit()


def load_shortlist(conn: sqlite3.Connection, session_id: str, include_removed: bool = False) -> list[RankedUnit]:
    clause = "" if include_removed else "AND si.is_removed = 0"
    rows = conn.execute(
        f"""SELECT si.*, u.*, p.name AS project_name, p.district AS district, p.handover_date AS handover_date
            FROM shortlist_item si
            JOIN unit u ON u.unit_id = si.unit_id
            JOIN project p ON p.project_id = u.project_id
            WHERE si.session_id = ? {clause}
            ORDER BY si.rank ASC""",
        (session_id,),
    ).fetchall()
    return [
        RankedUnit(
            unit=_unit_facts(row), match_score=row["match_score"],
            reasons=json.loads(row["reasons"]), tradeoffs=json.loads(row["tradeoffs"]),
        )
        for row in rows
    ]


def load_shortlist_internal(conn: sqlite3.Connection, session_id: str) -> list[RankedUnitInternal]:
    rows = conn.execute(
        """SELECT si.*, u.*, p.name AS project_name, p.district AS district, p.handover_date AS handover_date,
                  ub.business_priority, ub.days_on_market
           FROM shortlist_item si
           JOIN unit u ON u.unit_id = si.unit_id
           JOIN project p ON p.project_id = u.project_id
           JOIN unit_business ub ON ub.unit_id = u.unit_id
           WHERE si.session_id = ?
           ORDER BY si.rank ASC""",
        (session_id,),
    ).fetchall()
    return [
        RankedUnitInternal(
            unit=_unit_facts(row), match_score=row["match_score"],
            reasons=json.loads(row["reasons"]), tradeoffs=json.loads(row["tradeoffs"]),
            business_priority=row["business_priority"], days_on_market=row["days_on_market"],
            is_removed=bool(row["is_removed"]),
        )
        for row in rows
    ]


def remove_unit(conn: sqlite3.Connection, session_id: str, unit_id: str, reason: str) -> None:
    conn.execute(
        "UPDATE shortlist_item SET is_removed = 1 WHERE session_id = ? AND unit_id = ?",
        (session_id, unit_id),
    )
    audit(conn, session_id, actor_id=DEMO_SALE_USER_ID, action="remove_unit",
          unit_id=unit_id, reason_code="sale_removed", note=reason)


def reorder(conn: sqlite3.Connection, session_id: str, unit_id: str, new_rank: int, reason: str) -> None:
    old = conn.execute(
        "SELECT rank FROM shortlist_item WHERE session_id = ? AND unit_id = ?", (session_id, unit_id),
    ).fetchone()
    conn.execute(
        "UPDATE shortlist_item SET rank = ? WHERE session_id = ? AND unit_id = ?",
        (new_rank, session_id, unit_id),
    )
    audit(conn, session_id, actor_id=DEMO_SALE_USER_ID, action="override_rank",
          unit_id=unit_id, from_rank=old["rank"] if old else None, to_rank=new_rank,
          reason_code="sale_reorder", note=reason)


def approve(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute(
        "UPDATE session SET state = 'sent', sent_at = ?, updated_at = ? WHERE session_id = ?",
        (now(), now(), session_id),
    )
    audit(conn, session_id, actor_id=DEMO_SALE_USER_ID, action="approve_and_send")


def add_feedback(conn: sqlite3.Connection, session_id: str, unit_id: str, intent: str,
                  reason_tag: str | None, note: str | None) -> None:
    conn.execute(
        """INSERT INTO feedback (session_id, unit_id, intent, reason_tag, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (session_id, unit_id) DO UPDATE SET intent = excluded.intent,
               reason_tag = excluded.reason_tag, note = excluded.note, created_at = excluded.created_at""",
        (session_id, unit_id, intent, reason_tag, note, now()),
    )
    conn.commit()


def audit(
    conn: sqlite3.Connection, session_id: str, actor_id: int, action: str,
    unit_id: str | None = None, from_rank: int | None = None, to_rank: int | None = None,
    old_value: dict | None = None, new_value: dict | None = None,
    match_score: float | None = None, business_priority: float | None = None,
    days_on_market: int | None = None, reason_code: str | None = None, note: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO audit_log
           (session_id, actor_id, action, unit_id, from_rank, to_rank, old_value, new_value,
            match_score, business_priority, days_on_market, reason_code, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, actor_id, action, unit_id, from_rank, to_rank,
         json.dumps(old_value, ensure_ascii=False) if old_value else None,
         json.dumps(new_value, ensure_ascii=False) if new_value else None,
         match_score, business_priority, days_on_market, reason_code, note, now()),
    )
    conn.commit()

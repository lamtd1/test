"""Discovery agent — gọi Gemini thật (docs/adr/0002-gemini-for-discovery-agent.md).
Không tin thẳng output LLM: raw_quote phải là substring của câu khách nói, poi_id phải
nằm trong danh sách đã truyền vào prompt. Sai một trong hai thì bỏ field đó (không huỷ
cả request). Nếu gọi Gemini lỗi (mạng, quota, model bị sunset...) thì fallback về bộ
trích xuất regex nội bộ để agent vẫn hoạt động được.

Cấm bịa raw_quote: mọi soft_preference có source='user_stated' phải trích nguyên văn
từ chính câu khách nói. Không suy ra được thì source='agent_inferred', raw_quote=None.
"""

import json
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass, field

from src.config import get_settings
from src.models.criteria import CriteriaSchema, HardConstraints, SoftPreference

REQUIRED_FIELDS = ["bedrooms_min", "cash_available_vnd", "income_monthly_vnd"]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


@dataclass
class LlmUsage:
    node: str = "discovery"
    model: str = "fallback-regex"
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class DiscoveryResult:
    criteria: CriteriaSchema
    cash_available_vnd: int | None = None
    income_monthly_vnd: int | None = None
    existing_debt_monthly_vnd: int = 0
    llm_usage: LlmUsage = field(default_factory=LlmUsage)


# ---------- Gemini call ----------

_PROMPT_TEMPLATE = """Bạn là bộ trích xuất tiêu chí mua nhà cho một AI agent bất động sản.
Đọc câu khách nói, trả về DUY NHẤT một JSON object đúng cấu trúc sau (không thêm chữ nào khác):

{{
  "bedrooms_min": <int|null>,
  "cash_available_vnd": <int|null>,
  "income_monthly_vnd": <int|null>,
  "existing_debt_monthly_vnd": <int|null>,
  "near_poi_id": <int|null>,
  "near_poi_raw_quote": <string|null>,
  "wants_airy": <bool>,
  "wants_good_view": <bool>,
  "view_raw_quote": <string|null>
}}

Quy tắc bắt buộc:
- near_poi_id CHỈ được chọn từ danh sách POI dưới đây bằng đúng id số. Khách không nhắc
  địa điểm nào trong danh sách thì để null — KHÔNG tự bịa poi_id.
- near_poi_raw_quote và view_raw_quote PHẢI là đoạn trích NGUYÊN VĂN, liên tục, từ đúng
  câu khách nói bên dưới (không paraphrase, không dịch, không sửa dấu câu). Không trích
  được nguyên văn thì để null.
- Tiền tệ: "tỷ" = x1.000.000.000; "triệu" = x1.000.000. Khách nói một khoảng (vd
  "55-65 triệu") thì lấy trung bình, làm tròn.
- wants_airy = true nếu khách nhắc muốn thoáng/mát/nhiều gió/nhiều cửa sổ.
- wants_good_view = true nếu khách nhắc "view đẹp" hoặc tương đương.

Danh sách POI (id: tên):
{poi_list}

Câu khách nói: "{text}"
"""


def _call_gemini(text: str, pois: list[sqlite3.Row], model: str, api_key: str) -> tuple[dict, LlmUsage]:
    from google import genai
    from google.genai import types

    poi_list = "\n".join(f"{p['poi_id']}: {p['name']}" for p in pois)
    prompt = _PROMPT_TEMPLATE.format(poi_list=poi_list, text=text)

    client = genai.Client(api_key=api_key)
    start = time.perf_counter()
    last_error: Exception | None = None
    resp = None
    for attempt in range(2):  # 1 retry — Gemini "-latest" aliases occasionally 503 (high demand)
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            break
        except Exception as e:  # noqa: BLE001 — retried once, then re-raised to caller's fallback
            last_error = e
            if attempt == 0:
                time.sleep(0.6)
    if resp is None:
        raise last_error
    latency_ms = round((time.perf_counter() - start) * 1000)

    usage = resp.usage_metadata
    llm_usage = LlmUsage(
        model=model,
        tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
        tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
        cost_usd=0.0,  # chưa có bảng giá chính thức cho model "-latest", để 0 thay vì bịa số
        latency_ms=latency_ms,
    )
    return json.loads(resp.text), llm_usage


# ---------- fallback: regex/keyword (không gọi LLM) ----------

def _billion(text: str, keyword: str) -> int | None:
    m = re.search(rf"{keyword}[^\d]{{0,15}}([\d.,]+)\s*t[yỷ]", text, re.IGNORECASE)
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")) * 1_000_000_000)


def _million_range(text: str, keyword: str) -> int | None:
    m = re.search(
        rf"{keyword}[^\d]{{0,20}}([\d]+)(?:\s*[–\-to]{{1,3}}\s*([\d]+))?\s*tri[eệ]u",
        text, re.IGNORECASE,
    )
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return round((lo + hi) / 2 * 1_000_000)


def _bedrooms(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(phòng ngủ|pn)", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _find_poi(text: str, pois: list[sqlite3.Row]) -> sqlite3.Row | None:
    text_low = _strip_accents(text)
    best, best_overlap = None, 0
    for poi in pois:
        tokens = [t for t in re.split(r"\s+", _strip_accents(poi["name"])) if len(t) > 2]
        overlap = sum(1 for t in tokens if t in text_low)
        if overlap > best_overlap:
            best_overlap, best = overlap, poi
    return best if best_overlap >= 1 else None


def _regex_extract(text: str, pois: list[sqlite3.Row]) -> dict:
    poi = _find_poi(text, pois)
    near_poi_raw_quote = None
    if poi is not None:
        m = re.search(r"[^.]*g[aầ]n[^.]*", text, re.IGNORECASE)
        near_poi_raw_quote = m.group(0).strip() if m else text.strip()

    view_raw_quote = None
    wants_good_view = bool(re.search(r"view\s*đẹp|view.{0,10}đẹp", text, re.IGNORECASE))
    if wants_good_view:
        m = re.search(r"[^.]*view[^.]*", text, re.IGNORECASE)
        view_raw_quote = m.group(0).strip() if m else None

    return {
        "bedrooms_min": _bedrooms(text),
        "cash_available_vnd": _billion(text, "vốn tự có"),
        "income_monthly_vnd": _million_range(text, "thu nhập"),
        "existing_debt_monthly_vnd": _million_range(text, "nợ") or 0,
        "near_poi_id": poi["poi_id"] if poi is not None else None,
        "near_poi_raw_quote": near_poi_raw_quote,
        "wants_airy": bool(re.search(r"thoáng", text, re.IGNORECASE)),
        "wants_good_view": wants_good_view,
        "view_raw_quote": view_raw_quote,
    }


# ---------- assemble CriteriaSchema from validated extraction dict ----------

def _to_result(extracted: dict, text: str, pois: list[sqlite3.Row], llm_usage: LlmUsage) -> DiscoveryResult:
    poi_by_id = {p["poi_id"]: p for p in pois}
    text_low = _strip_accents(text)

    def valid_quote(q: str | None) -> str | None:
        if not q:
            return None
        return q if _strip_accents(q) in text_low else None

    hard = HardConstraints(bedrooms_min=extracted.get("bedrooms_min"))
    soft: list[SoftPreference] = []

    poi_id = extracted.get("near_poi_id")
    quote = valid_quote(extracted.get("near_poi_raw_quote"))
    if poi_id in poi_by_id and quote:
        poi = poi_by_id[poi_id]
        soft.append(SoftPreference(
            key="near_poi",
            params={"poi_id": poi_id, "poi_name": poi["name"], "ideal_m": 500, "max_m": 2000},
            weight=1.2, confidence="high", source="user_stated", raw_quote=quote,
        ))

    if extracted.get("wants_airy"):
        soft.append(SoftPreference(
            key="airiness", params={}, weight=0.8, confidence="low",
            source="agent_inferred", raw_quote=None,
        ))

    if extracted.get("wants_good_view"):
        quote = valid_quote(extracted.get("view_raw_quote"))
        soft.append(SoftPreference(
            key="view", params={"preferred": ["park", "lake", "river"]}, weight=0.6,
            confidence="low" if quote is None else "high",
            source="user_stated" if quote else "agent_inferred", raw_quote=quote,
        ))

    present = [v for v in [hard.bedrooms_min, extracted.get("cash_available_vnd"),
                            extracted.get("income_monthly_vnd")] if v is not None]
    completeness = round(len(present) / len(REQUIRED_FIELDS), 2)

    criteria = CriteriaSchema(
        hard_constraints=hard, soft_preferences=soft, deal_breakers=[],
        context={}, completeness=completeness,
    )
    return DiscoveryResult(
        criteria=criteria,
        cash_available_vnd=extracted.get("cash_available_vnd"),
        income_monthly_vnd=extracted.get("income_monthly_vnd"),
        existing_debt_monthly_vnd=extracted.get("existing_debt_monthly_vnd") or 0,
        llm_usage=llm_usage,
    )


def discover(text: str, pois: list[sqlite3.Row]) -> DiscoveryResult:
    settings = get_settings()
    if settings.google_api_key:
        try:
            extracted, llm_usage = _call_gemini(text, pois, settings.llm_model_discovery, settings.google_api_key)
            return _to_result(extracted, text, pois, llm_usage)
        except Exception:
            pass  # fallback dưới đây — agent vẫn phải trả lời được khi Gemini lỗi/quota/model sunset

    extracted = _regex_extract(text, pois)
    return _to_result(extracted, text, pois, LlmUsage(model="fallback-regex"))


MISSING_QUESTIONS = {
    "bedrooms_min": "Bạn muốn căn mấy phòng ngủ?",
    "cash_available_vnd": "Vốn tự có của bạn khoảng bao nhiêu?",
    "income_monthly_vnd": "Thu nhập hàng tháng của gia đình bạn khoảng bao nhiêu?",
}


def ask_next_question(result: DiscoveryResult) -> str | None:
    if result.criteria.hard_constraints.bedrooms_min is None:
        return MISSING_QUESTIONS["bedrooms_min"]
    if result.cash_available_vnd is None:
        return MISSING_QUESTIONS["cash_available_vnd"]
    if result.income_monthly_vnd is None:
        return MISSING_QUESTIONS["income_monthly_vnd"]
    return None

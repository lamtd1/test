from typing import Any, Literal

from pydantic import BaseModel, model_validator

SoftPreferenceKey = Literal["near_poi", "airiness", "view"]  # thêm formula mới thì mở rộng ở đây


class HardConstraints(BaseModel):
    area_min_m2: float | None = None
    bedrooms_min: int | None = None
    bathrooms_min: int | None = None
    floor_min: int | None = None
    district: list[str] | None = None
    price_max_vnd: int | None = None   # điền từ Envelope.price_max_vnd, KHÔNG từ lời khách


class SoftPreference(BaseModel):
    key: SoftPreferenceKey
    params: dict[str, Any] = {}
    weight: float = 1.0
    confidence: Literal["high", "low"] = "high"
    source: Literal["user_stated", "agent_inferred"]
    raw_quote: str | None = None

    @model_validator(mode="after")
    def raw_quote_required_when_user_stated(self):
        if self.source == "user_stated" and not self.raw_quote:
            raise ValueError("raw_quote is required when source='user_stated'")
        return self


class DealBreaker(BaseModel):
    key: str
    op: Literal["eq", "ne", "gte", "lte"]
    value: Any
    raw_quote: str | None = None


class CriteriaSchema(BaseModel):
    hard_constraints: HardConstraints = HardConstraints()
    soft_preferences: list[SoftPreference] = []
    deal_breakers: list[DealBreaker] = []
    context: dict[str, Any] = {}       # vd {"stated_budget_hint_vnd": 3_000_000_000} — tham khảo, không dùng để lọc/chấm điểm
    completeness: float = 0.0          # 0-1, agent tự đánh giá đã hỏi đủ field quan trọng chưa

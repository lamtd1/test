from pydantic import BaseModel


class UnitFacts(BaseModel):
    unit_id: str
    project_name: str
    district: str
    bedrooms: int
    bathrooms: int
    area_sqm: float
    floor: int
    total_floors: int
    balcony_dir: str | None
    view_type: str | None
    price_vnd: int
    handover_date: str | None  # từ project.handover_date; None = đã bàn giao


class RankedUnit(BaseModel):
    """Payload gửi cho khách. KHÔNG chứa business_priority/days_on_market/commission_pct —
    xem tests/test_business_priority_isolation.py."""
    unit: UnitFacts
    match_score: float
    reasons: list[str]
    tradeoffs: list[str]


class RankedUnitInternal(RankedUnit):
    """Payload cho role sale — thêm cột nội bộ. Chỉ dùng trong /review, không bao giờ
    trả qua /shortlist."""
    business_priority: float
    days_on_market: int
    is_removed: bool = False

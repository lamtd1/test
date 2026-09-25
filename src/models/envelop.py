from typing import Literal

from pydantic import BaseModel


class FinanceInput(BaseModel):
    """Đầu vào cho compute_envelope(). income đã được chuẩn hoá về 1 số
    (nếu khách khai khoảng, lấy trung bình TRƯỚC khi tạo object này)."""
    cash_available_vnd: int
    income_monthly_vnd: int
    existing_debt_monthly_vnd: int = 0
    loan_term_years: int = 25


class LeverageScenario(BaseModel):
    label: str                     # "an toàn" | "cân bằng" | "tối đa"
    ltv: float
    price_max_vnd: int
    installment_promo_vnd: int
    installment_float_vnd: int


class Envelope(BaseModel):
    price_min_vnd: int
    price_max_vnd: int
    price_target_vnd: int          # "vùng thoải mái" — do finance engine tự tính,
                                    # KHÔNG lấy từ số khách tự đoán ("tầm 3 tỷ")
    installment_promo_vnd: int
    installment_float_vnd: int
    binding_constraint: Literal["capacity", "equity"]  # DSR hay LTV quyết định trần
    income_bucket: str             # vd "50-60tr" — service tự tính, đây chỉ nhận str
    scenarios: list[LeverageScenario]
    disclaimer: str

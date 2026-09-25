"""
Engine tính vay đơn giản cho AI Agent gợi ý căn hộ.
Deterministic, không gọi LLM. LLM chỉ trích xuất input và diễn giải output.

Đơn vị tiền: VND. Lãi suất: số thập phân theo năm (0.09 = 9%/năm).

Mỗi ngân hàng có bộ tham số riêng (LTV/DSR/lãi suất khác nhau) nên KHÔNG đọc từ .env
(không có "1 giá trị toàn cục" đúng cho mọi bank) — mỗi bank là 1 `LoanPolicy` trong
list `BANKS`. Mở rộng ngân hàng mới: thêm 1 `LoanPolicy(bank_id=..., ...)` vào `BANKS`,
không cần sửa các hàm engine.

`BANKS[0]` (Techcombank) tham khảo công cụ ước tính khoản vay của TCB (23/09/2026):
lãi suất niêm yết 6,69%/năm, LTV 70%, dư nợ giảm dần — công cụ của TCB chỉ cho 1 mức lãi
duy nhất suốt kỳ hạn (không tách ưu đãi/thả nổi). `floating_rate` (lãi sau ưu đãi, dùng để
stress-test "vùng thoải mái") KHÔNG có trong số liệu TCB đã tra — đang để giả định +2,5 điểm %
so với `promo_rate` (mức chênh phổ biến trên thị trường), CẦN xác nhận lại với TCB.
Toàn bộ con số trong prototype chỉ mang tính tham khảo, không dùng để tư vấn thật.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from src.models.envelop import Envelope, LeverageScenario


class Method(StrEnum):
    EQUAL_PRINCIPAL = "du_no_giam_dan"  # gốc chia đều, lãi tính trên dư nợ còn lại (phổ biến ở VN)
    ANNUITY = "tra_gop_deu"             # tổng tiền trả mỗi tháng bằng nhau (trong cùng mức lãi)


@dataclass(frozen=True)
class LoanPolicy:
    """Bộ tham số vay của MỘT ngân hàng. Mỗi ngân hàng là 1 instance trong `BANKS` —
    không đọc từ .env, vì mỗi bank có bộ số khác nhau (không phải 1 giá trị toàn cục)."""
    bank_id: str = "tcb"
    bank_name: str = "Techcombank"
    max_ltv: float = 0.70             # Techcombank, công cụ ước tính 23/09/2026
    max_dsr: float = 0.40             # (nợ hiện có + tiền trả góp) / thu nhập tháng, ngưỡng cứng — chính sách nội bộ, không riêng của bank
    comfortable_dsr: float = 0.35     # dưới ngưỡng này thì "thoải mái"
    max_term_years: int = 25
    promo_rate: float = 0.0669        # lãi niêm yết Techcombank 23/09/2026
    promo_months: int = 24
    floating_rate: float = 0.0919     # TCB không công bố mức này, giả định
                                       # promo_rate + 2.5 điểm %, CẦN xác nhận lại
    closing_cost_rate: float = 0.025  # phí đi kèm (quỹ bảo trì, lệ phí trước bạ...) / giá căn
    method: Method = Method.EQUAL_PRINCIPAL


# Registry ngân hàng — thêm bank mới sau này chỉ cần append 1 LoanPolicy(...) vào đây,
# không sửa signature assess()/evaluate_unit()/to_envelope(). Hiện chỉ có Techcombank.
BANKS: list[LoanPolicy] = [
    LoanPolicy(),  # TCB — dùng default vì default đã đại diện cho TCB
]


def get_bank(bank_id: str) -> LoanPolicy:
    for bank in BANKS:
        if bank.bank_id == bank_id:
            return bank
    raise ValueError(f"Không có ngân hàng '{bank_id}' trong BANKS")


@dataclass
class Finance:
    savings: float                    # vốn tự có dùng được cho căn hộ
    monthly_income: float             # thu nhập ròng / tháng (cả hộ nếu vay chung)
    monthly_debt: float = 0           # các khoản trả nợ khác đang có / tháng
    term_years: int | None = None     # kỳ hạn khách muốn; None = tối đa theo policy


def _term_months(fin: Finance, p: LoanPolicy) -> int:
    years = min(fin.term_years or p.max_term_years, p.max_term_years)
    return years * 12


def schedule(loan: float, p: LoanPolicy, n: int) -> list[dict]:
    """Lịch trả nợ từng tháng. Lãi đổi từ promo sang thả nổi sau promo_months."""
    rows, bal = [], loan
    for m in range(1, n + 1):
        r = (p.promo_rate if m <= p.promo_months else p.floating_rate) / 12
        interest = bal * r
        if p.method == Method.EQUAL_PRINCIPAL:
            principal = loan / n
        else:  # annuity tính lại trên dư nợ và số kỳ còn lại
            k = n - m + 1
            principal = bal * r / (1 - (1 + r) ** -k) - interest
        bal -= principal
        rows.append({
            "month": m, "payment": principal + interest,
            "principal": principal, "interest": interest, "balance": max(bal, 0),
        })
    return rows


def _peak_payment_per_vnd(p: LoanPolicy, n: int) -> float:
    """Tiền trả tháng cao nhất cho mỗi 1 VND vay. Tiền trả tuyến tính theo khoản vay,
    nên max_loan = ngân sách trả hàng tháng / giá trị này."""
    return max(row["payment"] for row in schedule(1.0, p, n))


def assess(fin: Finance, p: LoanPolicy = BANKS[0]) -> dict:
    """Bước 1: khách mua được căn tối đa bao nhiêu tiền? Dùng làm hard filter cho truy vấn kho căn."""
    n = _term_months(fin, p)
    max_payment = max(fin.monthly_income * p.max_dsr - fin.monthly_debt, 0)
    max_loan_by_income = max_payment / _peak_payment_per_vnd(p, n)

    # Ràng buộc 1: vốn tự có phải đủ trả phần không được vay + phí
    price_by_equity = fin.savings / (1 - p.max_ltv + p.closing_cost_rate)
    # Ràng buộc 2: khoản vay (giá + phí - vốn) không vượt khả năng trả
    price_by_income = (max_loan_by_income + fin.savings) / (1 + p.closing_cost_rate)

    max_price = min(price_by_equity, price_by_income)
    return {
        "max_price": round(max_price),
        "binding_constraint": "von_tu_co" if price_by_equity < price_by_income else "thu_nhap",
        "price_by_equity": round(price_by_equity),
        "price_by_income": round(price_by_income),
        "max_monthly_payment": round(max_payment),
        "term_months": n,
    }


def evaluate_unit(price: float, fin: Finance, p: LoanPolicy = BANKS[0]) -> dict:
    """Bước 2: với từng căn cụ thể, tính khoản vay, tiền trả, DSR và phân loại."""
    n = _term_months(fin, p)
    total_cost = price * (1 + p.closing_cost_rate)
    loan = max(total_cost - fin.savings, 0)
    ltv = loan / price
    rows = schedule(loan, p, n) if loan else []
    first = rows[0]["payment"] if rows else 0
    peak = max(r["payment"] for r in rows) if rows else 0
    dsr_peak = (peak + fin.monthly_debt) / fin.monthly_income

    reasons = []
    if ltv > p.max_ltv:
        reasons.append(f"Thiếu vốn tự có {round(loan - p.max_ltv * price):,}đ (vay vượt {p.max_ltv:.0%} giá căn)")
    if dsr_peak > p.max_dsr:
        reasons.append(f"Tiền trả lúc cao nhất chiếm {dsr_peak:.0%} thu nhập (> {p.max_dsr:.0%})")

    if reasons:
        status = "khong_kha_thi"
    elif dsr_peak <= p.comfortable_dsr:
        status = "thoai_mai"
    else:
        status = "cang"

    return {
        "price": round(price), "loan": round(loan), "ltv": round(ltv, 3),
        "first_payment": round(first), "peak_payment": round(peak),
        "peak_month": max(rows, key=lambda r: r["payment"])["month"] if rows else None,
        "dsr_peak": round(dsr_peak, 3),
        "total_interest": round(sum(r["interest"] for r in rows)),
        "status": status, "reasons": reasons,
    }


def _income_bucket(monthly_income: float) -> str:
    """Quy tròn thu nhập về khoảng 10tr, KHÔNG lưu số thô. Vd 60tr -> '50-60tr'."""
    step_vnd = 10_000_000
    lo = (int(monthly_income) // step_vnd) * step_vnd
    hi = lo + step_vnd
    return f"{lo // 1_000_000}-{hi // 1_000_000}tr"


_LEVERAGE_SCENARIOS: tuple[tuple[str, float], ...] = (
    ("an toàn", 0.60),
    ("cân bằng", 0.70),
    ("tối đa", 0.80),
)


def _installments_at(price: int, fin: Finance, p: LoanPolicy) -> tuple[int, int]:
    """Trả góp tháng đầu (lãi ưu đãi) và trả góp ngay sau khi hết ưu đãi (lãi thả nổi),
    cho khoản vay ứng với `price`."""
    n = _term_months(fin, p)
    loan = max(price * (1 + p.closing_cost_rate) - fin.savings, 0)
    rows = schedule(loan, p, n) if loan else []
    if not rows:
        return 0, 0
    promo = round(rows[0]["payment"])
    float_idx = min(p.promo_months, len(rows) - 1)
    floating = round(rows[float_idx]["payment"])
    return promo, floating


def to_envelope(fin: Finance, p: LoanPolicy = BANKS[0]) -> Envelope:
    """Ghép assess() + schedule() thành Envelope (contract API/agent dùng).

    price_max = kịch bản lạc quan (lãi ưu đãi suốt kỳ hạn).
    price_min = kịch bản stress test (lãi thả nổi suốt kỳ hạn, không có ưu đãi).
    price_target = trung điểm — "vùng thoải mái" do engine tự tính, không lấy số khách tự đoán.
    """
    n = _term_months(fin, p)
    optimistic = replace(p, promo_rate=p.promo_rate, floating_rate=p.promo_rate, promo_months=n)
    pessimistic = replace(p, promo_rate=p.floating_rate, floating_rate=p.floating_rate, promo_months=n)

    price_max = assess(fin, optimistic)["max_price"]
    price_min = assess(fin, pessimistic)["max_price"]
    base = assess(fin, p)
    price_target = round((price_min + price_max) / 2)

    installment_promo, installment_float = _installments_at(base["max_price"], fin, p)

    scenarios = []
    for label, ltv in _LEVERAGE_SCENARIOS:
        scenario_policy = replace(p, max_ltv=ltv)
        scenario_price = assess(fin, scenario_policy)["max_price"]
        s_promo, s_float = _installments_at(scenario_price, fin, scenario_policy)
        scenarios.append(LeverageScenario(
            label=label, ltv=ltv, price_max_vnd=scenario_price,
            installment_promo_vnd=s_promo, installment_float_vnd=s_float,
        ))

    binding_constraint = "capacity" if base["binding_constraint"] == "thu_nhap" else "equity"

    return Envelope(
        price_min_vnd=price_min,
        price_max_vnd=price_max,
        price_target_vnd=price_target,
        installment_promo_vnd=installment_promo,
        installment_float_vnd=installment_float,
        binding_constraint=binding_constraint,
        income_bucket=_income_bucket(fin.monthly_income),
        scenarios=scenarios,
        disclaimer="Kết quả ước tính dựa trên thông tin bạn cung cấp và chính sách vay tham khảo, "
                    "không thay thế thẩm định chính thức của ngân hàng.",
    )

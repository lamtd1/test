"""Test cho finance engine. Số liệu tham chiếu trong test_schedule_equal_principal_matches_reference_table
lấy từ "Chi tiết khoản vay - 9232026.xlsx" (bảng amortization dư nợ giảm dần, vay 2,4 tỷ,
30 năm, 8,5%/năm, tính bằng Excel — dùng làm nguồn sự thật độc lập với code)."""

import pytest

from src.models.envelop import Envelope
from src.services.finance import (
    BANKS,
    Finance,
    LoanPolicy,
    Method,
    assess,
    evaluate_unit,
    get_bank,
    schedule,
    to_envelope,
)


def test_schedule_equal_principal_matches_reference_table():
    loan = 2_400_000_000
    n = 360
    # lãi cố định suốt kỳ hạn (không có ưu đãi/thả nổi) để khớp bảng Excel tham chiếu
    policy = LoanPolicy(promo_rate=0.085, floating_rate=0.085, promo_months=n, method=Method.EQUAL_PRINCIPAL)

    rows = schedule(loan, policy, n)

    assert len(rows) == n

    first = rows[0]
    assert first["month"] == 1
    assert first["interest"] == pytest.approx(17_000_000, rel=1e-6)
    assert first["principal"] == pytest.approx(6_666_666.667, rel=1e-6)
    assert first["payment"] == pytest.approx(23_666_666.667, rel=1e-6)
    assert first["balance"] == pytest.approx(2_393_333_333.333, rel=1e-6)

    last = rows[-1]
    assert last["month"] == 360
    assert last["interest"] == pytest.approx(47_222.222, rel=1e-6)
    assert last["principal"] == pytest.approx(6_666_666.667, rel=1e-6)
    assert last["payment"] == pytest.approx(6_713_888.889, rel=1e-6)
    assert last["balance"] == pytest.approx(0, abs=1e-3)

    total_interest = sum(r["interest"] for r in rows)
    total_principal = sum(r["principal"] for r in rows)
    assert total_interest == pytest.approx(3_068_500_000, rel=1e-6)
    assert total_principal == pytest.approx(2_400_000_000, rel=1e-6)


def test_schedule_annuity_payment_constant_within_rate_period_then_jumps():
    """Trả góp đều: payment không đổi trong 24 tháng ưu đãi, rồi nhảy bậc khi
    sang lãi thả nổi (tháng 25), khác EQUAL_PRINCIPAL vốn giảm dần đều."""
    policy = LoanPolicy(promo_rate=0.09, floating_rate=0.14, promo_months=24, method=Method.ANNUITY)
    rows = schedule(1_000_000_000, policy, 300)

    promo_payments = {round(r["payment"], 6) for r in rows[:24]}
    assert len(promo_payments) == 1  # tất cả các tháng ưu đãi trả cùng 1 số tiền

    assert rows[24]["payment"] > rows[23]["payment"]  # tháng 25 nhảy bậc do đổi rate
    assert rows[-1]["balance"] == pytest.approx(0, abs=1)


def test_assess_happy_case_binding_constraint_is_income_not_equity():
    """Kịch bản đích trong prototype-plan.md: vốn 1,2 tỷ, thu nhập 55-65tr (lấy TB 60tr),
    nợ 3tr/tháng. Với default policy, vốn tự có (1,2 tỷ) tương đối dồi dào so với thu nhập,
    nên trần phải do khả năng trả (thu nhập) quyết định — đúng câu chuyện "vì sao trần là số đó".

    Con số "2,50 tỷ" cụ thể trong prototype-plan.md phụ thuộc bộ tham số ngân hàng
    (lãi suất/DSR max) chưa được xác nhận với đối tác thật — không pin cứng vào đây."""
    fin = Finance(savings=1_200_000_000, monthly_income=60_000_000, monthly_debt=3_000_000, term_years=25)
    policy = LoanPolicy()

    result = assess(fin, policy)

    assert result["binding_constraint"] == "thu_nhap"
    assert result["max_price"] > 0
    assert result["price_by_income"] == result["max_price"]


def test_assess_more_debt_lowers_max_price():
    """Nợ hiện có tăng -> ngân sách trả góp còn lại giảm -> trần giá giảm.
    Đây là bất biến quan trọng nhất của engine tài chính: trần phải phản ánh đúng
    hướng thay đổi của input, không phụ thuộc vào việc pin đúng 1 con số tuyệt đối."""
    p = LoanPolicy()
    low_debt = assess(Finance(savings=1_200_000_000, monthly_income=60_000_000, monthly_debt=1_000_000), p)
    high_debt = assess(Finance(savings=1_200_000_000, monthly_income=60_000_000, monthly_debt=20_000_000), p)

    assert high_debt["max_price"] < low_debt["max_price"]


def test_evaluate_unit_flags_price_over_income_capacity():
    """Căn vượt quá khả năng trả (DSR đỉnh > max_dsr) phải bị đánh dấu không khả thi,
    kèm lý do cụ thể."""
    fin = Finance(savings=1_200_000_000, monthly_income=60_000_000, monthly_debt=3_000_000, term_years=25)
    policy = LoanPolicy()

    result = evaluate_unit(price=6_000_000_000, fin=fin, p=policy)

    assert result["status"] == "khong_kha_thi"
    assert result["reasons"]


def test_to_envelope_produces_valid_schema_with_optimistic_max_and_stress_tested_min():
    """price_max (lạc quan, lãi ưu đãi suốt kỳ) phải >= price_min (bi quan, lãi thả nổi
    suốt kỳ — stress test). Đây là 'vùng thoải mái' README nhắc tới, không phải con số
    khách tự đoán."""
    fin = Finance(savings=1_200_000_000, monthly_income=62_000_000, monthly_debt=3_000_000, term_years=25)

    envelope = to_envelope(fin, LoanPolicy())

    assert isinstance(envelope, Envelope)
    assert envelope.price_min_vnd <= envelope.price_target_vnd <= envelope.price_max_vnd
    assert envelope.installment_promo_vnd < envelope.installment_float_vnd
    assert envelope.binding_constraint in ("capacity", "equity")
    assert len(envelope.scenarios) == 3
    assert envelope.income_bucket == "60-70tr"
    assert envelope.disclaimer


def test_banks_registry_has_techcombank_loaded_first():
    """BANKS là list (không phải đọc env) để sau này thêm ngân hàng khác chỉ cần append,
    không sửa signature các hàm engine."""
    assert BANKS[0].bank_id == "tcb"
    assert BANKS[0].bank_name == "Techcombank"
    assert BANKS[0].promo_rate == pytest.approx(0.0669)


def test_get_bank_looks_up_by_id_and_raises_for_unknown():
    assert get_bank("tcb") is BANKS[0]
    with pytest.raises(ValueError):
        get_bank("khong_ton_tai")

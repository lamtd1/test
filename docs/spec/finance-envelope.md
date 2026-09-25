# Spec: Finance envelope

**Trạng thái:** Implemented (`src/services/finance.py`, không đổi khi refactor schema)

## Mục tiêu
Tính trần giá mua được + khoản trả góp, deterministic (không LLM). Chi tiết công thức
LTV/DSR/niên kim/stress-test đã có trong docstring của `finance.py` — spec này chỉ ghi
hợp đồng API và điểm neo với schema mới.

## Hợp đồng
`to_envelope(Finance, LoanPolicy) -> Envelope` — không đổi. `POST /sessions/{id}/finance`
nhận `FinanceInput`, lưu `session.envelope` (JSON) + `session.income_bucket`
(`'50-60tr'`, KHÔNG lưu số thô — đúng nguyên tắc #3 trong `docs/schemas.md`).

## Điểm neo với schema mới
- `session.finance_purged_at`: chưa có endpoint xoá dữ liệu tài chính (khách bấm "xoá
  thông tin tài chính") — cột đã có trong schema, logic chưa viết.
- `income_monthly_vnd`/`cash_available_vnd` chỉ tồn tại trong request body lúc tính, và
  trong tham số truyền cho `Finance` — không có bảng nào lưu số thô.

## Chưa làm
- Endpoint xoá dữ liệu tài chính (set `finance_purged_at`, xoá `session.envelope`).

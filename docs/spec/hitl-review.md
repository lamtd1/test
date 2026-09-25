# Spec: HITL review (sale console)

**Trạng thái:** Implemented (`src/api/routes.py`, `src/services/session_store.py`)

## Mục tiêu
Sale xem shortlist trước khi khách thấy, sửa được nhưng mọi thao tác có side effect
phải để lại vết trong `audit_log`.

## Endpoints
- `GET /api/v1/queue` — phiên `state='awaiting_review'`, sắp theo `created_at`.
- `GET /api/v1/sessions/{id}/review` — criteria + envelope + shortlist kèm cột nội bộ
  (`business_priority`, `days_on_market` từ `unit_business`).
- `PATCH /api/v1/sessions/{id}/criteria` — sửa criteria → chạy lại `retrieve()` +
  `explain()`, ghi `audit_log(action='update_criteria')`.
- `POST /api/v1/sessions/{id}/units/{unit_id}/remove` — `is_removed=true` (không xoá
  dòng), bắt buộc `reason` → `audit_log(action='remove_unit', reason_code, note)`.
- `POST /api/v1/sessions/{id}/reorder` — đổi `rank`, bắt buộc `reason` (422 nếu thiếu) →
  `audit_log(action='override_rank', from_rank, to_rank, reason_code, note)`.
- `POST /api/v1/sessions/{id}/approve` — `state='sent'`, `sent_at=now()`.

## Ràng buộc chống thiên vị
`GET /shortlist` (customer) không bao giờ join `unit_business` — cấu trúc code, không
phải quy ước nhớ xoá field. Test:
`tests/test_business_priority_isolation.py`.

## Chưa làm
- `add_unit` (sale thêm căn ngoài shortlist do hệ thống gợi ý) — bảng `shortlist_item`
  đã có cột `origin`/`over_envelope` cho việc này nhưng endpoint chưa viết.
- Hậu kiểm tương quan `match_score` ↔ `days_on_market` (theo README) — cần dữ liệu chạy
  thật, không làm được trên mock tĩnh.

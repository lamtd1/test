# 0004: SQLite reseed-on-boot thay vì migrate Supabase ngay

Trạng thái: Đã chấp nhận (2026-09-25)

## Bối cảnh

Deploy backend lên Render. Render (free tier) xoá filesystem mỗi lần
redeploy/restart, nên file SQLite (`data/app.db`) không sống sót qua các
lần deploy. Hai hướng: (a) migrate sang Supabase (Postgres managed, có
sẵn từ đầu trong `docs/schemas.md`), hoặc (b) giữ SQLite và reseed lại
từ `data/*.csv` mỗi lần container khởi động.

## Quyết định

Giữ SQLite, reseed lại toàn bộ DB từ `data/*.csv` mỗi lần container boot
(`scripts/seed.py` chạy trước `uvicorn` trong Dockerfile CMD — xem
docs/superpowers/specs/2026-09-25-cicd-render-vercel-design.md).

## Vì sao

- `docs/schemas.md` vốn viết cho Postgres nên việc migrate sau này (khi
  cần) không mất công viết lại schema, chỉ cần đổi driver + kiểm lại
  CHECK constraint trên Postgres — hoãn lại không tốn chi phí kỹ thuật.
- Đây vẫn là prototype phục vụ demo/happy-case, không có dữ liệu người
  dùng thật cần giữ lại giữa các lần deploy.
- Không cần trả phí Render persistent disk hay set up Supabase project
  ngay khi chưa cần độ bền dữ liệu.

## Đánh đổi

- Mọi session/shortlist/audit_log tạo ra giữa 2 lần deploy sẽ mất khi
  redeploy — chấp nhận được cho giai đoạn demo, không chấp nhận được
  nếu có buổi demo trực tiếp với sale/khách hàng thật kéo dài và deploy
  giữa chừng.
- Khi cần nhiều instance/scale ngang, SQLite (một file, một tiến trình)
  sẽ không còn phù hợp — lúc đó bắt buộc phải migrate Postgres/Supabase.

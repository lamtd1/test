# ADR 0001: SQLite thay Postgres cho prototype

**Trạng thái:** Chấp nhận

**Bối cảnh:** `docs/schemas.md` và README chỉ định PostgreSQL + pgvector làm database
đích. Máy dev hiện tại có Docker cài nhưng daemon không chạy, nên không dựng được
Postgres ngay để build happy-case prototype.

**Quyết định:** Dùng SQLite (`data/app.db`, qua `sqlite3` stdlib) cho prototype, với
schema dịch 1-1 từ `docs/schemas.md` (bảng, cột, CHECK constraint giữ nguyên tên và ý
nghĩa). Không dùng ORM.

**Vì sao:**
- Không cần Docker/service ngoài — `python -m scripts.seed` chạy trong <1s, ai cũng
  dựng được không cần cài thêm gì.
- Đủ cho quy mô mock (~40 căn, ~100 dòng distance) — không cần pgvector/PostGIS.
- Schema dịch sát nghĩa (JSONB → cột TEXT chứa JSON, xử lý ở tầng Python; mảng → JSON
  array trong TEXT; UUID → TEXT) nên chuyển sang Postgres thật sau này chỉ là đổi
  `src/db.py` + driver, không đổi model Pydantic hay logic service.

**Đánh đổi:** Không có ràng buộc JSONB native, không full-text/vector search, không
chạy được đồng thời nhiều writer an toàn — chấp nhận được cho một prototype single-user
demo.

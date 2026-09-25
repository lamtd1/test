# HomeMatch

> Khách mô tả nhu cầu mơ hồ và sale phải lọc tay hàng trăm căn → AI Agent phỏng vấn, tính năng lực tài chính thật rồi xếp hạng gợi ý kèm lý giải đánh đổi, có sale duyệt trước khi trình → cho **sale bán căn hộ** và **người mua nhà lần đầu**.

## Vấn đề (Problem)

**Ai đang gặp vấn đề.** Sale dự án quản lý 40–60 lead cùng lúc trên kho ~400 căn thuộc 6 dự án, mỗi căn có hàng chục thuộc tính. Khách mua — phần lớn mua lần đầu — mô tả nhu cầu bằng ngôn ngữ đời thường: *"gần trường, thoáng, tầm 3 tỷ, view đẹp"*.

**Tốn bao nhiêu.** Từ lúc khách nêu nhu cầu tới khi có shortlist mất **hàng giờ đến vài ngày** vì sale phải dịch nhu cầu sang tiêu chí trong đầu rồi lọc tay. Mỗi phút lọc tay là một phút không gọi điện được cho lead khác. Tệ hơn, shortlist thường vỡ ở bước tài chính: khách chốt được căn rồi mới phát hiện không vay nổi, mất công cả hai bên từ đầu.

**Vì sao giải pháp hiện tại chưa đủ.**
- **Filter trên web bất động sản** đòi khách tự dịch *"thoáng"* thành tầng và hướng ban công — khách không có ngôn ngữ đó. Không có filter nào cho *"gần trường con em học"*.
- **Sale lọc tay** chỉ phủ được vài chục căn quen thuộc; phần còn lại của kho không bao giờ được đề xuất.
- **Chatbot FAQ** trả lời câu hỏi chung, không truy vấn kho và không tính được khách vay được bao nhiêu.
- **Máy tính lãi vay của ngân hàng** cho một con số trả góp, không nói vì sao trần là con số đó, và không nối được với kho căn.
- Khách không có cách kiểm chứng vì sao được gợi ý căn này, nên **có lý do nghi ngờ sale đang đẩy hàng tồn**.

## Giải pháp (Solution)

- **Discovery Agent phỏng vấn thay vì form.** Khách nói tự nhiên, agent hỏi lại tối đa 8 lượt (một câu một lượt) và điền `Criteria Schema` có cấu trúc. Mỗi tiêu chí gắn `confidence`, `source` và `raw_quote` — trích nguyên văn lời khách, chống hallucinate và làm nguyên liệu cho phần giải thích.
- **Affordability Engine trả lời "vì sao trần là con số đó".** Code deterministic, không LLM: LTV, DSR, niên kim, stress test. Trả trần giá **kèm ràng buộc quyết định trần** (khả năng trả hay vốn tự có), cả hai mức trả góp trước/sau ưu đãi, và 3 kịch bản đòn bẩy trả lời câu khách hay hỏi — *"làm sao mua được căn tốt hơn?"*. Kết quả trả cho khách ngay, không chờ sale duyệt.
- **Ranking giải thích bằng fact, không bằng điểm.** *"Tầng 18/25, ban công Đông Nam, cách Tiểu học X 600m — vượt vùng thoải mái của bạn 9%"* thay cho *"độ phù hợp 86%"*. Mọi câu phải truy vết được về một field trong DB, và **tradeoff là bắt buộc** — căn không có nhược điểm là dấu hiệu hệ thống đang bán hàng chứ không tư vấn.
- **HITL console cho sale.** Sale sửa tiêu chí agent hiểu sai (chạy lại xếp hạng), loại căn, thêm căn của mình, đổi thứ hạng — nhưng **đổi hạng và thêm căn bắt buộc nhập lý do**, ghi vào audit log cùng cả hai điểm số.
- **Hai điểm số tách biệt để chống thiên vị căn tồn.** `match_score` mù hoàn toàn với tồn kho và hoa hồng; `business_priority` chỉ tồn tại trong payload của role `sale`. Kiểm bằng test tự động, và hậu kiểm bằng tương quan giữa `match_score` và `days_on_market`.
- **So sánh trực quan + feedback loop.** Bảng so sánh tối đa 3 căn với ô khác biệt được làm nổi và một dòng "Đánh đổi chính"; sau đó khách chọn căn muốn đi xem và gắn tag lý do loại từng căn.

## Target User

- **Primary: Sale dự án** — người dùng kinh tế, ra quyết định cuối và chịu trách nhiệm trước khách về danh sách mình trình. Cần shortlist nhanh mà **đứng tên được**: mỗi căn phải kèm lý do giải thích được cho khách. Ngưỡng chấp nhận: phải sửa quá nửa danh sách thì quay về lọc tay.
- **Secondary: Người mua căn hộ lần đầu** — người dùng thụ hưởng. Chưa biết mình mua được tầm nào, ngại khai thu nhập chính xác cho một chatbot, không có ngôn ngữ chuyên môn để mô tả thứ mình muốn. Cần biết năng lực tài chính thật **trước khi** đi xem nhà.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + GPT-4o (Discovery, structured output) · `gpt-4o-mini` (sinh lý giải) |
| Retrieval | SQL lọc cứng → scoring bằng code → pgvector (`text-embedding-3-small`, tính offline) |
| Finance | Python thuần, không LLM — LTV · DSR · niên kim · stress test |
| Backend | FastAPI + Python 3.11+ |
| Frontend | React + Vite + TypeScript + Tailwind |
| Database | PostgreSQL + pgvector (khoảng cách bằng haversine, không cần PostGIS) |
| DevOps | Docker + GitHub Actions + Render (backend) + Vercel (frontend) |

> **Prototype hiện tại chạy trên phiên bản rút gọn của stack trên** — xem "Quick Start"
> ngay dưới đây để biết khác biệt (SQLite thay Postgres/pgvector, Gemini thay GPT-4o,
> React+Vite tối giản không Tailwind). Lý do từng lựa chọn: `docs/adr/`. Database schema
> chuẩn: `docs/schemas.md` (dịch sang SQLite trong `src/db.py`).

## Quick Start (prototype hiện tại)

Prototype dùng **SQLite** (không cần Docker/Postgres) và **Discovery agent gọi Gemini
thật** (`google-genai`, model `gemini-flash-lite-latest`, fallback về regex nếu Gemini
lỗi/quota) — xem `docs/adr/0001-*.md`, `docs/adr/0002-*.md` cho lý do, `docs/spec/` cho
chi tiết từng feature.

```bash
# 1. Backend
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirement.txt
# Điền GOOGLE_API_KEY thật vào .env (lấy tại aistudio.google.com/apikey)
python -m scripts.seed            # nạp data/*.csv (mock: 6 dự án, 16 POI, 40 căn) vào data/app.db
uvicorn src.main:app --reload     # http://localhost:8000/docs

# 2. Frontend (terminal khác)
cd web && npm install && npm run dev   # http://localhost:5173
```

Hoặc dùng Makefile: `make seed`, `make run` (backend), `make web` (frontend).

**Lưu ý khi test lại nhiều lần:** mỗi lần `python -m scripts.seed` sẽ xoá và tạo lại
`data/app.db` — `session_id` cũ lưu trong `localStorage` của trình duyệt sẽ trỏ vào
phiên không còn tồn tại. Frontend tự phát hiện lỗi 404 này và tạo phiên mới (xem
`web/src/lib/session.ts`), nên chỉ cần thao tác lại từ `/chat` là được, không cần xoá
`localStorage` tay.

Không có tài khoản đăng nhập ở bản prototype này — mỗi trình duyệt tự tạo 1 session
(lưu `session_id` trong `localStorage`). Trang `/sale/queue` liệt kê mọi session đang
`awaiting_review`.

Kịch bản happy-case để test (dán vào `/chat`): *"Mình muốn căn 2 phòng ngủ gần trường
tiểu học Nam Từ Liêm, thoáng một chút. Vốn tự có 1,2 tỷ, thu nhập hai vợ chồng tầm
55–65 triệu, đang trả nợ 3 triệu mỗi tháng."*

## Environment Variables

Khai báo đầy đủ trong `.env.example`, **không chứa giá trị thật**. `.gitignore` chặn `.env`, `.venv/`, `node_modules/`, `data/raw/`.

| Variable | Description |
|---|---|
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL (cần extension `vector`) |
| `JWT_SECRET` / `JWT_EXPIRE_MINUTES` | Secret ký token · hạn token (mặc định 120) |
| `OPENAI_API_KEY` | Key gọi GPT-4o — chỉ đặt trong `.env` local hoặc Render Environment |
| `CORS_ORIGINS` | Danh sách origin frontend được phép gọi API, phân tách bằng dấu phẩy (backend, mặc định `http://localhost:5173,http://127.0.0.1:5173`) |
| `LLM_MODEL_DISCOVERY` | Model cho Discovery node (mặc định `gpt-4o`) |
| `LLM_MODEL_EXPLAIN` | Model sinh reasons/tradeoffs (mặc định `gpt-4o-mini`) |
| `EMBEDDING_MODEL` | Model embedding mô tả căn, chạy offline (mặc định `text-embedding-3-small`) |
| `VECTOR_TOP_K` | Số ứng viên lấy ra ở bước pgvector (mặc định 20) |
| `OVERPASS_API_URL` | Endpoint OSM Overpass lấy POI (chỉ dùng lúc build dataset) |
| `FIN_LTV_MAX` / `FIN_DSR_MAX` | Tham số tài chính, cấu hình được (0.70 / 0.40) |
| `FIN_RATE_PROMO` / `FIN_RATE_FLOAT` | Lãi ưu đãi / thả nổi (9% / 14% — mặt bằng 9/2026) |
| `SESSION_RETENTION_DAYS` | Hạn giữ dữ liệu phiên (mặc định 90) |
| `PUBLIC_BASE_URL` | Domain public trên Render, dùng cho link gửi khách |
| `VITE_API_URL` | Base URL của backend API mà frontend gọi tới (frontend/Vercel, ví dụ `https://<service>.onrender.com/api/v1`) |

## Deploy (Render + Vercel)

Push-to-deploy is wired via each platform's native GitHub integration —
GitHub Actions only runs the CI gate (`.github/workflows/ci.yml`), it does
not perform the deploys itself.

**Backend (Render), one-time setup:**
1. Render dashboard → New → Blueprint → connect `lamtd1/test`. Render reads
   `render.yaml` and creates the `homematch-api` web service automatically.
2. In the service's Environment tab, set the secrets marked `sync: false`
   in `render.yaml`: `GOOGLE_API_KEY` (your Gemini key) and `CORS_ORIGINS`
   (leave blank until Vercel gives you a URL in step 2 below, then come
   back and fill it in, comma-separated if you have both a production and
   a preview domain).
3. Every push to `main` redeploys automatically; the container reseeds
   SQLite from `data/*.csv` on every boot (see
   `docs/adr/0004-sqlite-reseed-on-render.md`), so demo data is always
   fresh, not persisted between deploys.

**Frontend (Vercel), one-time setup:**
1. Vercel dashboard → Add New → Project → import `lamtd1/test`, set Root
   Directory to `web`. Vercel auto-detects the Vite build.
2. Project → Settings → Environment Variables → add `VITE_API_URL` =
   `https://<your-render-service>.onrender.com/api/v1`.
3. Every push to `main` deploys to production; every PR gets a preview
   URL automatically.
4. Copy the resulting Vercel production URL back into Render's
   `CORS_ORIGINS` env var (step 2 above) so the backend accepts requests
   from it.

## Project Structure

```
├── src/
│   ├── agent/                # (scaffold cho LangGraph — chưa dùng trong prototype)
│   ├── api/routes.py         # FastAPI routes (customer · sale)
│   ├── models/                # Pydantic schemas (CriteriaSchema, Envelope, RankedUnit)
│   ├── services/               # finance engine · discover (mock) · retrieval · explain · session_store
│   ├── db.py                   # SQLite schema + haversine
│   ├── config.py                # Settings
│   └── main.py                   # App entry point
├── web/                     # React + Vite + TypeScript (Chat · Finance · Shortlist · SaleQueue · SaleReview)
├── scripts/seed.py         # Nạp data/*.csv vào SQLite
├── data/                     # projects.csv · pois.csv · units.csv (mock)
├── tests/                     # Test suite (gồm test chống rò rỉ business_priority)
├── docs/                      # prototype-plan · architecture
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/sessions` | Tạo phiên mới |
| POST | `/api/v1/sessions/{id}/messages` | Chat với agent → reply + criteria schema + completeness |
| POST | `/api/v1/sessions/{id}/finance` | Tính affordability envelope |
| POST | `/api/v1/sessions/{id}/scenarios` | Lấy lại kịch bản vay |
| GET | `/api/v1/sessions/{id}/shortlist` | Shortlist cho khách — **không chứa `business_priority`** |
| POST | `/api/v1/sessions/{id}/feedback` | Căn muốn đi xem + tag lý do loại |
| GET | `/api/v1/queue` | Hàng chờ duyệt (role `sale`) |
| GET | `/api/v1/sessions/{id}/review` | Schema + shortlist + cột nội bộ (role `sale`) |
| PATCH | `/api/v1/sessions/{id}/criteria` | Sale sửa tiêu chí → chạy lại ranking |
| POST | `/api/v1/sessions/{id}/units/{unit_id}/remove` | Loại căn khỏi shortlist (cần lý do) |
| POST | `/api/v1/sessions/{id}/reorder` | Đổi thứ hạng — 422 nếu thiếu lý do |
| POST | `/api/v1/sessions/{id}/approve` | Duyệt & gửi khách → state `sent` |
| GET | `/api/v1/audit` | Audit log theo phiên |

## Deliverables Checklist

- [x] Source Code (GitHub)
- [x] README.md
- [ ] Architecture Diagram (`docs/architecture_diagram.md`)
- [ ] AI Logs (`AI_LOG.md`)
- [ ] Live URL / Deploy
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [ ] Weekly Journal (`JOURNAL.md`)
- [ ] Worklog (`WORKLOG.md`)
- [ ] Evaluation Evidence (`eval/results/`)

## Documentation

- [Các bước build prototype](./docs/prototype-plan.md) — 9 bước, có tiêu chí "xong khi"
- [Architecture](./docs/architecture/architecture.md)
- [Schema chuẩn](./docs/schemas.md) — nguồn sự thật cho data model, `src/db.py` dịch từ đây
- [ADR](./docs/adr/) — quyết định kỹ thuật giữa 2 lựa chọn (DB engine, LLM provider, frontend)
- [Spec](./docs/spec/) — hợp đồng + phạm vi từng feature (discovery agent, retrieval, HITL, finance)

## Workflow

- `main` luôn ở trạng thái demo được. Feature branch: `feature/<short-name>`.
- PR trước khi merge; ít nhất 1 người khác review phần quan trọng.
- Commit message: `feat:` `fix:` `docs:` `test:` `chore:` `refactor:`.
- Tag mốc: `v0.2-localhost` · `v0.3-production` · `v0.5-handoff`.

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| Tạ Duy Lâm | Web / UI · merge & final check | 2A202602699 |
| Nguyễn Xuân Khuê | AI / Agent (LangGraph, prompt, eval) | 2A202602999 |
| Lê Công Tâm | Backend / Finance · deploy | 2A202602406 |
| Nguyễn Quang Đạo | Data (kho căn, POI, scoring, pgvector) | 2A202602394 |

## License

MIT

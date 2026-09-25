# HomeMatch — Các bước build prototype (happy case)

Mục tiêu duy nhất: **một luồng chạy thật từ câu nói của khách tới shortlist đã được sale duyệt.** Mọi thứ không phục vụ mục tiêu đó đều để sau.

Kịch bản đích, chạy được nguyên văn:

> *"Mình muốn căn 2 phòng ngủ gần trường tiểu học Nam Từ Liêm, thoáng một chút. Vốn tự có 1,2 tỷ, thu nhập hai vợ chồng tầm 55–65 triệu, đang trả nợ 3 triệu mỗi tháng."*
>
> → tầm giá **2,13 – 2,50 tỷ** · trả góp 13,7tr → 19,0tr · top 5 căn kèm lý do và đánh đổi → sale duyệt → khách nhận shortlist.

Kiến trúc và sơ đồ luồng: [architecture_diagram.md](./architecture_diagram.md).

---

## Nguyên tắc ghép

1. **Chốt hợp đồng dữ liệu trước khi ai viết logic.** Bước 0 là việc của cả nhóm, làm cùng nhau trong một buổi.
2. **Lát cắt dọc, không làm theo tầng.** Sau mỗi bước, luồng chạy được đầu–cuối dù thô. Không ai làm xong 100% phần mình rồi mới ghép.
3. **Fake trước, thật sau.** Bước nào chưa có thì trả dữ liệu cứng đúng kiểu dữ liệu. Web gọi API thật từ ngày đầu, dù API trả hàng cố định.
4. **Một câu lệnh chạy được toàn bộ.** Ai clone repo về cũng dựng được trong 5 phút, nếu không thì demo sẽ vỡ.

---

## Bước 0 — Hợp đồng dữ liệu · cả nhóm · nửa ngày

Chốt ba thứ, viết ra file, không ai sửa một mình sau đó.

- `src/models/criteria.py` — `CriteriaSchema` bằng Pydantic: `hard_constraints`, `soft_preferences[]` (mỗi phần tử có `key`, `params`, `weight`, `confidence`, `source`, `raw_quote`), `deal_breakers[]`, `context`, `completeness`.
- `src/models/envelope.py` — `FinanceInput` và `Envelope`. Copy từ `finance.py` đã có.
- `docs/schema.sql` — đã có, chạy thử một lần để chắc dựng được.

**Xong khi:** cả 4 người `from src.models.criteria import CriteriaSchema` chạy không lỗi, và mỗi người nói được hàm của mình nhận gì trả gì.

---

## Bước 1 — Kho hàng seed · Đạo · 1 ngày

- Chọn **6 dự án thật ở Nam Từ Liêm và Cầu Giấy**, lấy toạ độ từ Google Maps, điền tay vào `data/projects.csv`.
- Lấy POI quanh 2 quận từ Overpass: trường tiểu học, công viên, siêu thị, bệnh viện — khoảng 15–20 điểm, vào `data/pois.csv`.
- Sinh **40 căn** vào `data/units.csv`, phân bố có chủ đích:
  - ≥ 12 căn 2PN trong khoảng **2,0 – 2,5 tỷ** (để happy case có kết quả)
  - 2–3 căn hướng Tây (để có tradeoff thật)
  - 2–3 căn bàn giao 2027 (tradeoff thời điểm)
  - **0 căn 3PN ở Cầu Giấy dưới 2,8 tỷ** (để fail case "không căn nào thoả" kích hoạt được)
- `scripts/seed.py` nạp 3 CSV vào Postgres và **tính sẵn** `project_poi_distance` bằng `haversine_m`.

**Xong khi:** `python -m scripts.seed` chạy từ DB trắng, và `SELECT count(*) FROM project_poi_distance` ra đúng 6 × số POI.

---

## Bước 2 — Tài chính thành endpoint · Tâm · nửa ngày

- Đặt `finance.py` vào `src/services/`, `test_finance.py` vào `tests/`. 17 test phải xanh.
- `POST /api/v1/sessions` → tạo phiên, trả `session_id`.
- `POST /api/v1/sessions/{id}/finance` → gọi `compute_envelope`, lưu `envelope` + `income_bucket` vào `session`, trả `Envelope`.
- **Không lưu số thu nhập thô.** Chỉ lưu bucket dạng `'50-60tr'`.

**Xong khi:** `curl` với đúng input của kịch bản trả về `price_max` ≈ 2,50 tỷ và `binding_constraint: "capacity"`.

---

## Bước 3 — Lọc và chấm điểm · Đạo · 1,5 ngày

`src/services/retrieval.py` — một hàm: `retrieve(criteria, envelope) -> list[ScoredUnit]`.

- **Lọc cứng bằng SQL**: `status='available'`, `bedrooms >= n`, `price_vnd <= envelope.price_max`, `district IN (...)`, loại `deal_breakers` (ví dụ `balcony_dir IS DISTINCT FROM 'W'`).
- **Chấm điểm bằng Python** trên kết quả:
  - `near_poi`: `clamp(1 − (d − ideal)/(max − ideal), 0, 1)` — lấy `d` từ `project_poi_distance`
  - `airiness`: `0.4·(floor/total_floors) + 0.4·dir_bonus + 0.2·(n_open_sides/3)`
  - `view`: vị trí `view_type` trong danh sách ưu tiên của khách
- `match_score = Σ(weight × score) / Σweight`; preference `confidence: low` nhân 0.7.
- Hàm này **không nhận** `business_priority` làm tham số. Có một test khẳng định điều đó.

**Xong khi:** nhập tay một `CriteriaSchema` qua CLI → ra top 5 có điểm, thứ tự giải thích được bằng tay.

---

## Bước 4 — Lý do bằng template · Đạo · nửa ngày

`src/services/explain.py` — không gọi LLM ở bước này.

```python
reasons.append(f"Cách {poi.name} {d}m — đi bộ {d // 75} phút")
reasons.append(f"Tầng {u.floor}/{u.total_floors}, ban công {DIR_VI[u.balcony_dir]}, {u.n_open_sides} mặt thoáng")
if u.price_vnd > env.price_target:
    over = (u.price_vnd / env.price_target - 1) * 100
    tradeoffs.append(f"Giá {ty(u.price_vnd)} — vượt vùng thoải mái của bạn {over:.0f}%")
```

Quy tắc: mỗi câu phải sinh từ **một field cụ thể**. Không có field thì không có câu. Mỗi căn bắt buộc ≥ 1 tradeoff; không tìm ra thì ghi *"không có đánh đổi đáng kể so với tiêu chí của bạn"*.

**Xong khi:** `GET /api/v1/sessions/{id}/shortlist` trả 5 căn, mỗi căn có 2–3 `reasons` và ≥ 1 `tradeoffs`, và payload **không chứa** `business_priority`.

---

## Bước 5 — Web tối thiểu 2 vai · Lâm · 2 ngày, song song từ bước 2

Ba trang khách, hai trang sale. Không router phức tạp, không thư viện state.

- `/chat` — ô nhập + bong bóng hội thoại + panel "hệ thống đang hiểu" (đọc từ `session.criteria`).
- `/finance` — form vốn / khoảng thu nhập / nợ / kỳ hạn → thẻ tầm giá, **hai mức trả góp**, câu `binding_constraint`, 3 kịch bản, disclaimer.
- `/shortlist` — poll 3 giây; `state != 'sent'` thì hiện màn chờ kèm tầm giá; `sent` thì hiện 5 thẻ căn.
- `/sale/queue` — bảng phiên chờ.
- `/sale/review/{id}` — schema bên trái, 5 căn ở giữa, **cột nội bộ bên phải**, nút *Loại* và *Duyệt & gửi*.

Từ ngày đầu gọi API thật. Chưa có endpoint thì backend trả hàng cố định đúng kiểu — đừng mock trong frontend.

**Xong khi:** bấm hết luồng bằng chuột, không mở DevTools, không sửa code.

---

## Bước 6 — Discovery agent · Khuê · 1,5 ngày

`src/services/discover.py` — chỗ duy nhất gọi OpenAI.

- `gpt-4o`, structured output theo đúng `CriteriaSchema`, `temperature=0`.
- Prompt bắt buộc: mỗi `soft_preference` phải có `confidence`, `source`, `raw_quote`; **cấm bịa `raw_quote`**; suy luận thì `source: agent_inferred`.
- Tên trường/POI phải chọn từ danh sách `poi` truyền vào prompt, không tự sinh.
- Một lượt trích xuất trước. Xong rồi thêm `ask_next_question(schema)`: thiếu field nào quan trọng nhất thì hỏi đúng một câu về nó.
- Ghi `llm_usage` mỗi lời gọi.

**Xong khi:** dán nguyên câu trong kịch bản → schema hợp lệ, `bedrooms_min = 2`, có `near_poi` trỏ đúng `poi_id` của TH Nam Từ Liêm, `airiness` có `source: agent_inferred`.

---

## Bước 7 — HITL · Tâm · 1 ngày

- `GET /api/v1/queue` — phiên `awaiting_review`, sắp theo thời gian chờ, kèm tóm tắt nhu cầu + tầm giá. **Không trả `cash_needed_upfront`** — sale không được thấy tiết kiệm gốc của khách.
- `GET /api/v1/sessions/{id}/review` — schema + 5 căn + cột nội bộ (join `unit_business`).
- `POST /api/v1/sessions/{id}/units/{unit_id}/remove` — đánh `is_removed = true`, không xoá dòng.
- `POST /api/v1/sessions/{id}/approve` — `state = 'sent'`, ghi `sent_at`.

**Xong khi:** sale duyệt → trong 3 giây màn khách tự đổi từ màn chờ sang shortlist.

---

## Bước 8 — Chạy bằng một câu lệnh · Tâm · nửa ngày

`docker-compose.yml` dựng Postgres; `Makefile` hoặc `run.sh` làm: dựng DB → migrate → seed → chạy API → chạy web. `.env.example` đủ biến, không có key thật.

**Xong khi:** một người trong nhóm clone repo về máy trắng, chạy một lệnh, bấm hết luồng.

---

## Thứ tự và song song

| Ngày | Đạo | Tâm | Khuê | Lâm |
|---|---|---|---|---|
| 1 | Bước 0 (cả nhóm) | Bước 0 | Bước 0 | Bước 0 |
| 2 | Seed CSV + script | Endpoint tài chính | Prompt + thử structured output | Dựng app, 3 trang rỗng |
| 3 | Lọc cứng + chấm điểm | API trả hàng cố định cho Lâm | Trích xuất một lượt | Trang chat + trang tài chính |
| 4 | Template lý do | HITL queue + review | Hỏi lại field thiếu | Trang shortlist + poll |
| 5 | Ghép với API thật | Approve + đổi state | Ghi `llm_usage` | Trang sale |
| 6 | Chạy thử toàn luồng | Docker + one-command | Sửa prompt theo kết quả thật | Sửa UI theo kết quả thật |

---

## Xong prototype khi cả 5 câu này đúng

1. Dán nguyên câu kịch bản vào ô chat → hệ thống hiểu đúng 2PN và trường tiểu học.
2. Nhập tài chính → thấy **2,13 – 2,50 tỷ**, thấy cả 13,7tr và 19,0tr, thấy câu *"trần của bạn do khả năng trả quyết định"*.
3. Thấy màn chờ, không thấy danh sách căn.
4. Sale mở console, thấy schema + 5 căn + cột nội bộ, bấm *Duyệt & gửi*.
5. Màn khách tự đổi sang shortlist, mỗi căn có lý do dạng fact và ít nhất một đánh đổi.

Đủ 5 câu là dừng, không thêm tính năng. Việc tiếp theo là bốn fail case, rồi mới đến deploy.
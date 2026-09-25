# HomeMatch — Architecture (prototype)

Phạm vi tài liệu này là **prototype chạy happy case**, không phải kiến trúc production. Những chỗ đơn giản hoá có ghi rõ ở mục 5.

---

## 1. Sơ đồ khối

```mermaid
flowchart TB
    subgraph CLIENT["Trình duyệt"]
        WK["Web khách<br/>React + Vite :5173<br/>/chat · /finance · /shortlist"]
        WS["Web sale<br/>cùng app, route /sale<br/>/queue · /review"]
    end

    subgraph API["Backend — FastAPI :8000 (một process)"]
        R1["api/customer.py<br/>POST /sessions<br/>POST /messages<br/>POST /finance<br/>GET /shortlist"]
        R2["api/sale.py<br/>GET /queue<br/>GET /review<br/>POST /approve"]

        subgraph PIPE["services/ — 4 hàm thuần, gọi tuần tự"]
            N1["discover()<br/>text → CriteriaSchema"]
            N2["qualify()<br/>tài chính → Envelope"]
            N3["retrieve()<br/>SQL + chấm điểm"]
            N4["explain()<br/>fact → reasons/tradeoffs"]
        end
    end

    subgraph DATA["PostgreSQL :5432"]
        T1[("project · unit · poi<br/>project_poi_distance")]
        T2[("unit_business<br/>chỉ sale đọc")]
        T3[("session · message<br/>shortlist_item")]
    end

    OA["OpenAI API<br/>gpt-4o · structured output"]

    WK --> R1
    WS --> R2
    R1 --> N1
    R1 --> N2
    R1 --> N3
    N3 --> N4
    N1 <-->|"1 lời gọi / lượt"| OA
    N3 --> T1
    N2 -.->|"không đụng DB kho"| T3
    R1 --> T3
    R2 --> T3
    R2 --> T2
    R2 --> T1

    classDef nollm fill:#E3EFEB,stroke:#1F6F63
    classDef biz fill:#EDEBE4,stroke:#8C8A81
    class N2,N3,N4 nollm
    class T2 biz
```

**Ô xanh = không gọi LLM.** Chỉ `discover()` gọi OpenAI. Tài chính, lọc, chấm điểm, sinh lý do đều là code thuần — nên prototype chạy được cả khi mất mạng ra OpenAI (dùng form thay chat).

**Ô xám `unit_business`** chỉ có `api/sale.py` đọc. `api/customer.py` không import model đó — rò rỉ `business_priority` bị chặn bằng cấu trúc.

---

## 2. Luồng happy case

```mermaid
sequenceDiagram
    autonumber
    actor KH as Khách
    participant W as Web
    participant A as FastAPI
    participant L as GPT-4o
    participant F as Finance (code)
    participant DB as Postgres
    actor SL as Sale

    KH->>W: "2PN gần TH Nam Từ Liêm, thoáng"
    W->>A: POST /sessions/{id}/messages
    A->>L: extract_criteria(text)
    L-->>A: CriteriaSchema (JSON)
    A->>DB: lưu message + session.criteria
    A-->>W: schema + completeness

    KH->>W: vốn 1,2 tỷ · thu nhập 55–65tr · nợ 3tr
    W->>A: POST /sessions/{id}/finance
    A->>F: compute_envelope()
    F-->>A: Envelope (price_max 2,50 tỷ)
    A->>DB: lưu envelope + income_bucket
    A-->>W: Envelope
    W-->>KH: hiện tầm giá NGAY, không chờ sale

    A->>DB: SELECT lọc cứng + JOIN khoảng cách
    DB-->>A: ~40 căn ứng viên
    A->>A: chấm điểm bằng code → top 5
    A->>A: sinh reasons/tradeoffs từ template
    A->>DB: ghi shortlist_item · state = awaiting_review

    SL->>A: GET /queue
    A-->>SL: phiên #4821 · tóm tắt + tầm giá
    SL->>A: GET /sessions/4821/review
    A-->>SL: schema + 5 căn + cột nội bộ
    SL->>A: POST /sessions/4821/approve
    A->>DB: state = sent
    W->>A: GET /shortlist (poll 3s)
    A-->>W: 5 căn + lý do
    W-->>KH: shortlist đã duyệt
```

---

## 3. Dữ liệu biến đổi qua các bước

```mermaid
flowchart LR
    T["Câu nói tự nhiên<br/>'2PN gần trường, thoáng'"]
    --> CS["CriteriaSchema<br/>hard: bedrooms≥2<br/>soft: near_poi(1042), airiness<br/>mỗi field có confidence/source/raw_quote"]
    CS --> HC["+ price_max từ Envelope<br/>→ hard_constraints đầy đủ"]
    HC --> SQL["SQL WHERE<br/>status · bedrooms · price · district<br/>JOIN project_poi_distance"]
    SQL --> SC["Chấm điểm bằng code<br/>score_poi = clamp(1−(d−500)/1500)<br/>score_airy = 0.4·tầng + 0.4·hướng + 0.2·mặt thoáng"]
    SC --> TOP["match_score = Σ(w·s)/Σw<br/>→ top 5"]
    TOP --> EX["Template lý do<br/>f'Cách {poi} {d}m'<br/>f'Tầng {floor}/{total}, ban công {dir}'"]
```

Điểm cần nhớ: **LLM chỉ biến đổi *câu hỏi*, không biến đổi *dữ liệu***. Kho căn giữ nguyên fact gốc.

---

## 4. Ai sở hữu phần nào

| Vùng | File | Owner | Contract với phần khác |
|---|---|---|---|
| Hợp đồng dữ liệu | `src/models/criteria.py` · `envelope.py` | Khuê | **Chốt trước tất cả.** Mọi người import từ đây |
| Kho + truy vấn | `src/services/retrieval.py` · `scoring.py` · `scripts/seed.py` | Đạo | Nhận `CriteriaSchema` + `Envelope` → trả `list[RankedUnit]` |
| Tài chính + API | `src/services/finance.py` · `src/api/*` | Tâm | Đã xong `finance.py`; chỉ bọc endpoint |
| Agent | `src/services/discover.py` | Khuê | Nhận `str` + schema hiện tại → trả `CriteriaSchema` |
| Web | `web/src/**` | Lâm | Chỉ gọi 6 endpoint ở mục 2, không gọi DB |

Bốn người làm song song được vì **contract là 3 kiểu dữ liệu**, không phải là code của nhau.

---

## 5. Những chỗ đơn giản hoá ở prototype

| Thật ra nên | Prototype làm | Vì sao chấp nhận được |
|---|---|---|
| JWT, 2 role | Header `X-Role: customer\|sale` + 2 user seed | Auth không phải thứ demo chứng minh |
| WebSocket đẩy shortlist | Poll `GET /shortlist` mỗi 3s | Đủ cho demo, ít code hơn nhiều |
| LLM diễn đạt lý do | Template f-string | Grounding 100% theo định nghĩa, không tốn token, không hallucinate |
| LangGraph 4 node | 4 hàm Python gọi tuần tự | Cùng chữ ký; bọc vào graph sau mất nửa ngày |
| pgvector cho tiêu chí mơ hồ | Không có | Tiêu chí đã phân rã thành công thức; chưa cần |
| Hội thoại nhiều lượt | Một lượt trích xuất, thiếu field thì hỏi lại 1 câu | Nhiều lượt là bước tiếp theo |
| Sale sửa tiêu chí, đổi hạng có lý do | Chỉ *duyệt* và *loại căn* | Đủ thoả HITL ở mức prototype |
| Docker Compose + Railway | `uvicorn` + `npm run dev` + Postgres trong Docker | Deploy là việc của W3 |

---

*Tài liệu liên quan: [Các bước build prototype](./prototype-plan.md) · [PRD](./prd.md) · [1-Page Brief](./brief.md)*
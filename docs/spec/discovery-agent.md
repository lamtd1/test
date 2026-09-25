# Spec: Discovery agent

**Trạng thái:** Implemented (`src/services/discover.py`)

## Mục tiêu
Chuyển câu nói tự nhiên của khách thành `CriteriaSchema` có cấu trúc, không bịa dữ
liệu, và hỏi lại đúng 1 câu khi thiếu field bắt buộc.

## Input / Output
- Input: `text: str` (một lượt chat), danh sách `pois` (id + name, từ bảng `poi`).
- Output: `DiscoveryResult { criteria: CriteriaSchema, cash_available_vnd, income_monthly_vnd,
  existing_debt_monthly_vnd, llm_usage }`.

## Cách làm
1. Gọi Gemini (`gemini-flash-latest`, `response_mime_type=application/json`) với danh
   sách POI được nhúng vào prompt — model chỉ được chọn `poi_id` từ danh sách này, không
   tự sinh tên trường/POI.
2. Validate ở tầng Python trước khi tin bất kỳ trường nào từ LLM:
   - `raw_quote` (nếu có) phải là substring của chính `text` gốc (so khớp bỏ dấu) —
     không thì bị loại, coi như `agent_inferred`/`raw_quote=None`.
   - `poi_id` phải tồn tại trong danh sách đã truyền vào.
3. Nếu gọi Gemini lỗi (mạng, quota, model bị sunset...): fallback về bộ trích xuất
   regex/keyword nội bộ (`_regex_extract`) để agent vẫn hoạt động được — ghi
   `llm_usage.model = "fallback-regex"`.
4. `ask_next_question()` là logic Python thuần (không LLM): field nào trong
   `REQUIRED_FIELDS` còn thiếu thì hỏi đúng 1 câu, theo thứ tự cố định.

## Ràng buộc cấm bịa
- `SoftPreference.source == "user_stated"` bắt buộc có `raw_quote` hợp lệ (Pydantic
  validator trong `src/models/criteria.py`).
- Field suy luận (không trích được câu gốc) phải gắn `source: agent_inferred`,
  `raw_quote: null`.

## Chưa làm (out of scope prototype)
- Multi-turn context dài hơn 1 lượt gần nhất khi trích xuất (agent hiện gộp criteria
  cũ + mới ở tầng route, không phải agent tự nhớ hội thoại).
- Đánh giá completeness bằng LLM — hiện tính bằng tỷ lệ field bắt buộc đã có.

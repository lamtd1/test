# ADR 0002: Gemini thay OpenAI cho Discovery agent

**Trạng thái:** Chấp nhận

**Bối cảnh:** README/Tech Stack gốc chọn GPT-4o cho Discovery (structured output). Ban
đầu prototype dùng bộ trích xuất regex/keyword mock (không gọi LLM thật) để chạy được
happy case không cần key. Người dùng sau đó cung cấp Gemini API key thật và yêu cầu gọi
API thật.

**Hai lựa chọn:**
1. **OpenAI GPT-4o/4o-mini** — đúng tech stack gốc trong README, nhưng không có key
   thật trong `.env` (chỉ có placeholder).
2. **Google Gemini** — có key thật hoạt động (xác minh bằng `GET /v1beta/models`), hỗ
   trợ `response_mime_type=application/json` cho struct output tương đương OpenAI
   structured output.

**Quyết định:** Dùng Gemini (`google-genai` SDK) cho Discovery agent. Model:
`gemini-flash-latest` — alias "latest" tránh việc pin cứng một version cụ thể rồi bị
Google sunset (đã gặp `gemini-2.5-flash`/`gemini-2.5-pro` trả 404 "no longer available
to new users" ngay trong lúc build).

**Vì sao không tiếp tục OpenAI:** Không có key thật để test; đổi provider không đổi
kiến trúc (Discovery vẫn là 1 node duy nhất gọi LLM, input/output vẫn là
`CriteriaSchema`) nên chi phí đổi lại sau này thấp nếu cần.

**Đánh đổi:** README/Tech Stack ghi GPT-4o — cần cập nhật khi có OpenAI key thật, hoặc
giữ Gemini nếu Gemini đáp ứng đủ. `raw_quote` vẫn được validate ở tầng Python (phải là
substring của câu khách nói) trước khi tin — không tin thẳng output LLM, bất kể provider
nào.

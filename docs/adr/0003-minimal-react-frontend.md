# ADR 0003: React+Vite tối giản thay Next.js+shadcn

**Trạng thái:** Chấp nhận

**Bối cảnh:** README/Tech Stack gốc chọn React+Vite+TypeScript+Tailwind. Giữa chừng
build, người dùng đề nghị đổi sang Next.js+shadcn/ui rồi tự đổi ý ngay sau đó, chốt
"minimum react".

**Hai lựa chọn:**
1. **Next.js + shadcn/ui** — component đẹp sẵn, routing/SSR mạnh hơn, nhưng thêm
   dependency lớn (Next runtime, Tailwind config, shadcn CLI init) cho một prototype 5
   trang chỉ cần click-through được.
2. **Vite + React + TypeScript, không Tailwind/router library** — 1 file CSS thuần, 1
   router tự viết ~40 dòng (path + query qua `window.history`), không SSR.

**Quyết định:** Vite + React + TS tối giản, CSS thuần, router tự viết.

**Vì sao:** Prototype chỉ cần 5 trang đơn giản (chat, finance, shortlist, sale queue,
sale review) không cần SSR/SEO; thêm Next.js + shadcn tốn thời gian setup (config
Tailwind, khởi tạo shadcn, chọn component) mà không đổi được gì về mặt chức năng cho
happy-case demo. Giảm bề mặt phụ thuộc = ít điểm hỏng hơn khi demo.

**Đánh đổi:** Không có component library — UI thô, cần polish lại nếu dùng cho pitch/
demo thật. Không router thật (không hỗ trợ nested routes, loaders...) — đủ cho 5 trang
phẳng hiện tại, sẽ cần thay nếu số trang tăng.

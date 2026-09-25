import { useEffect, useRef, useState } from "react";
import { api, type CriteriaSchema } from "../lib/api";
import { withSession } from "../lib/session";
import { Link } from "../lib/router";

interface Bubble {
  role: "user" | "agent";
  text: string;
}

export default function Chat() {
  const [bubbles, setBubbles] = useState<Bubble[]>([
    { role: "agent", text: "Chào bạn! Hãy mô tả căn hộ bạn đang tìm — càng tự nhiên càng tốt." },
  ]);
  const [input, setInput] = useState("");
  const [criteria, setCriteria] = useState<CriteriaSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles]);

  async function send() {
    if (!input.trim()) return;
    const text = input.trim();
    setBubbles((b) => [...b, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await withSession((sessionId) => api.sendMessage(sessionId, text));
      setBubbles((b) => [...b, { role: "agent", text: res.reply }]);
      setCriteria(res.criteria);
    } catch (e) {
      setBubbles((b) => [...b, { role: "agent", text: `Lỗi: ${(e as Error).message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page chat-page">
      <div className="chat-column">
        <h1>Trò chuyện với Discovery Agent</h1>
        <div className="chat-window">
          {bubbles.map((b, i) => (
            <div key={i} className={`bubble bubble-${b.role}`}>
              {b.text}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Mô tả nhu cầu của bạn..."
            disabled={loading}
          />
          <button onClick={send} disabled={loading}>
            {loading ? "..." : "Gửi"}
          </button>
        </div>
        <Link to="/finance" className="next-link">
          Tiếp theo: tính tài chính →
        </Link>
      </div>
      <aside className="panel">
        <h2>Hệ thống đang hiểu</h2>
        {!criteria && <p className="muted">Chưa có thông tin.</p>}
        {criteria && (
          <>
            <p>
              <b>Phòng ngủ tối thiểu:</b> {criteria.hard_constraints.bedrooms_min ?? "—"}
            </p>
            <p>
              <b>Độ hoàn thiện:</b> {(criteria.completeness * 100).toFixed(0)}%
            </p>
            <b>Sở thích:</b>
            <ul>
              {criteria.soft_preferences.map((p, i) => (
                <li key={i}>
                  <code>{p.key}</code> — nguồn: {p.source}
                  {p.raw_quote && <div className="quote">"{p.raw_quote}"</div>}
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}

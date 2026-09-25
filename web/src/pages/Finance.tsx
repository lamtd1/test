import { useState } from "react";
import { api, formatVnd, formatVndMonthly, type Envelope } from "../lib/api";
import { withSession } from "../lib/session";
import { Link } from "../lib/router";

export default function Finance() {
  const [cash, setCash] = useState("1200000000");
  const [income, setIncome] = useState("60000000");
  const [debt, setDebt] = useState("3000000");
  const [term, setTerm] = useState("25");
  const [envelope, setEnvelope] = useState<Envelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      const res = await withSession((sessionId) =>
        api.computeFinance(sessionId, {
          cash_available_vnd: Number(cash),
          income_monthly_vnd: Number(income),
          existing_debt_monthly_vnd: Number(debt),
          loan_term_years: Number(term),
        }),
      );
      setEnvelope(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <h1>Khả năng tài chính</h1>
      <div className="form-grid">
        <label>
          Vốn tự có (VND)
          <input value={cash} onChange={(e) => setCash(e.target.value)} />
        </label>
        <label>
          Thu nhập / tháng (VND)
          <input value={income} onChange={(e) => setIncome(e.target.value)} />
        </label>
        <label>
          Nợ hiện có / tháng (VND)
          <input value={debt} onChange={(e) => setDebt(e.target.value)} />
        </label>
        <label>
          Kỳ hạn vay (năm)
          <input value={term} onChange={(e) => setTerm(e.target.value)} />
        </label>
      </div>
      <button onClick={submit} disabled={loading}>
        {loading ? "Đang tính..." : "Tính tầm giá"}
      </button>
      {error && <p className="error">{error}</p>}

      {envelope && (
        <div className="envelope-card">
          <h2>
            Tầm giá: {formatVnd(envelope.price_min_vnd)} – {formatVnd(envelope.price_max_vnd)}
          </h2>
          <p>
            Trả góp: <b>{formatVndMonthly(envelope.installment_promo_vnd)}</b>/tháng (lãi ưu đãi) → sau đó{" "}
            <b>{formatVndMonthly(envelope.installment_float_vnd)}</b>/tháng (lãi thả nổi)
          </p>
          <p>
            Trần của bạn do{" "}
            <b>{envelope.binding_constraint === "capacity" ? "khả năng trả" : "vốn tự có"}</b> quyết định.
          </p>
          <h3>Kịch bản đòn bẩy</h3>
          <table>
            <thead>
              <tr>
                <th>Kịch bản</th>
                <th>LTV</th>
                <th>Giá tối đa</th>
                <th>Trả góp ưu đãi</th>
                <th>Trả góp thả nổi</th>
              </tr>
            </thead>
            <tbody>
              {envelope.scenarios.map((s) => (
                <tr key={s.label}>
                  <td>{s.label}</td>
                  <td>{(s.ltv * 100).toFixed(0)}%</td>
                  <td>{formatVnd(s.price_max_vnd)}</td>
                  <td>{formatVndMonthly(s.installment_promo_vnd)}</td>
                  <td>{formatVndMonthly(s.installment_float_vnd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="disclaimer">{envelope.disclaimer}</p>
          <Link to="/shortlist" className="next-link">
            Xem shortlist →
          </Link>
        </div>
      )}
    </div>
  );
}

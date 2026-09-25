import { useEffect, useState } from "react";
import { api, formatVnd, type CriteriaSchema, type Envelope, type RankedUnitInternal } from "../lib/api";
import { useRouter } from "../lib/router";

export default function SaleReview() {
  const { query } = useRouter();
  const sessionId = query.get("session") ?? "";
  const [criteria, setCriteria] = useState<CriteriaSchema | null>(null);
  const [envelope, setEnvelope] = useState<Envelope | null>(null);
  const [units, setUnits] = useState<RankedUnitInternal[]>([]);
  const [state, setState] = useState("");
  const [approved, setApproved] = useState(false);

  async function load() {
    if (!sessionId) return;
    const res = await api.getReview(sessionId);
    setCriteria(res.criteria);
    setEnvelope(res.envelope);
    setUnits(res.units);
    setState(res.state);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  async function remove(unitId: string) {
    const reason = window.prompt("Lý do loại căn này?");
    if (!reason) return;
    await api.removeUnit(sessionId, unitId, reason);
    load();
  }

  async function doApprove() {
    await api.approve(sessionId);
    setApproved(true);
    load();
  }

  if (!sessionId) return <div className="page">Thiếu session id.</div>;

  return (
    <div className="page review-page">
      <aside className="panel">
        <h2>Schema</h2>
        {criteria && (
          <>
            <p>
              <b>Phòng ngủ tối thiểu:</b> {criteria.hard_constraints.bedrooms_min ?? "—"}
            </p>
            <p>
              <b>Giá tối đa:</b> {formatVnd(criteria.hard_constraints.price_max_vnd)}
            </p>
            <ul>
              {criteria.soft_preferences.map((p, i) => (
                <li key={i}>{p.key} ({p.source})</li>
              ))}
            </ul>
          </>
        )}
        {envelope && (
          <p>
            Tầm giá: {formatVnd(envelope.price_min_vnd)} – {formatVnd(envelope.price_max_vnd)}
          </p>
        )}
        <p>
          Trạng thái: <b>{state}</b>
        </p>
      </aside>

      <div className="unit-list">
        <h1>Shortlist ({units.filter((u) => !u.is_removed).length} căn)</h1>
        <table>
          <thead>
            <tr>
              <th>Căn</th>
              <th>Giá</th>
              <th>Match score</th>
              <th>Business priority</th>
              <th>Ngày trên thị trường</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {units.map((u) => (
              <tr key={u.unit.unit_id} className={u.is_removed ? "removed" : ""}>
                <td>
                  {u.unit.project_name} — {u.unit.unit_id}
                </td>
                <td>{formatVnd(u.unit.price_vnd)}</td>
                <td>{u.match_score.toFixed(2)}</td>
                <td className="internal-col">{u.business_priority.toFixed(2)}</td>
                <td className="internal-col">{u.days_on_market}</td>
                <td>
                  {!u.is_removed && (
                    <button onClick={() => remove(u.unit.unit_id)}>Loại</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <button className="approve-btn" onClick={doApprove} disabled={state === "sent"}>
          {state === "sent" ? "Đã duyệt & gửi" : "Duyệt & gửi"}
        </button>
        {approved && <p className="success">Đã gửi cho khách.</p>}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { api, formatVnd, type RankedUnit } from "../lib/api";
import { withSession } from "../lib/session";

export default function Shortlist() {
  const [state, setState] = useState<string>("collecting");
  const [priceRange, setPriceRange] = useState<{ min?: number | null; max?: number | null }>({});
  const [units, setUnits] = useState<RankedUnit[]>([]);

  useEffect(() => {
    let timer: number;
    let cancelled = false;

    async function poll() {
      const res = await withSession((sessionId) => api.getShortlist(sessionId));
      if (cancelled) return;
      setState(res.state);
      if (res.state === "sent" && res.units) {
        setUnits(res.units);
      } else {
        setPriceRange({ min: res.price_min_vnd, max: res.price_max_vnd });
      }
      timer = window.setTimeout(poll, 3000);
    }

    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  if (state !== "sent") {
    return (
      <div className="page waiting-page">
        <h1>Đang chờ sale duyệt...</h1>
        <p>Tầm giá của bạn: {formatVnd(priceRange.min)} – {formatVnd(priceRange.max)}</p>
        <div className="spinner" />
        <p className="muted">Trang này tự cập nhật mỗi 3 giây.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Shortlist của bạn</h1>
      <div className="unit-grid">
        {units.map((u) => (
          <div className="unit-card" key={u.unit.unit_id}>
            <h3>
              {u.unit.project_name} — {u.unit.unit_id}
            </h3>
            <p className="price">{formatVnd(u.unit.price_vnd)}</p>
            <p className="muted">
              {u.unit.bedrooms}PN · {u.unit.area_sqm}m² · Tầng {u.unit.floor}/{u.unit.total_floors}
            </p>
            <div className="reasons">
              <b>Lý do</b>
              <ul>
                {u.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
            <div className="tradeoffs">
              <b>Đánh đổi</b>
              <ul>
                {u.tradeoffs.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

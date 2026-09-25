import { useEffect, useState } from "react";
import { api, formatVnd } from "../lib/api";
import { Link } from "../lib/router";

interface QueueItem {
  session_id: string;
  created_at: string;
  price_min_vnd: number;
  price_max_vnd: number;
}

export default function SaleQueue() {
  const [items, setItems] = useState<QueueItem[]>([]);

  useEffect(() => {
    api.getQueue().then((res) => setItems(res.queue));
  }, []);

  return (
    <div className="page">
      <h1>Hàng chờ duyệt</h1>
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>Tạo lúc</th>
            <th>Tầm giá</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.session_id}>
              <td>
                <code>{it.session_id.slice(0, 8)}</code>
              </td>
              <td>{new Date(it.created_at).toLocaleString("vi-VN")}</td>
              <td>
                {formatVnd(it.price_min_vnd)} – {formatVnd(it.price_max_vnd)}
              </td>
              <td>
                <Link to={`/sale/review?session=${it.session_id}`}>Xem</Link>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                Không có phiên nào đang chờ.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

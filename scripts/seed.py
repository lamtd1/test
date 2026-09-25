"""Nạp data/*.csv vào SQLite theo schema docs/schemas.md, tính sẵn project_poi_distance
bằng haversine, và sinh unit_business + app_user mock. Chạy: python -m scripts.seed
"""

import csv
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db as db_module  # noqa: E402
from src.db import get_conn, haversine_m, init_schema  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FURNISHING_DEFAULT = {"1": "bare", "2": "basic", "3": "full"}


def _read_csv(name: str) -> list[dict]:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def seed() -> None:
    if db_module.DB_PATH.exists():
        db_module.DB_PATH.unlink()

    conn = get_conn()
    init_schema(conn)

    projects = _read_csv("project.csv")
    conn.executemany(
        """INSERT INTO project
           (project_id, name, developer, district, ward, lat, lng, geo_source,
            handover_date, amenities, is_synthetic)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                p["project_id"], p["name"], p["developer"] or None, p["district"], p["ward"] or None,
                p["lat"], p["lng"], p["geo_source"], p["handover_date"] or None,
                json.dumps(p["amenities"].split("|") if p["amenities"] else [], ensure_ascii=False),
                int(p["is_synthetic"]),
            )
            for p in projects
        ],
    )

    pois = _read_csv("poi.csv")
    conn.executemany(
        "INSERT INTO poi (type, name, lat, lng, osm_id) VALUES (?, ?, ?, ?, ?)",
        [(p["type"], p["name"], p["lat"], p["lng"], p["osm_id"] or None) for p in pois],
    )
    poi_ids = [row["poi_id"] for row in conn.execute("SELECT poi_id FROM poi ORDER BY poi_id").fetchall()]

    units = _read_csv("unit.csv")
    created_at = _now()
    for u in units:
        provenance = {
            k: "synthetic" for k in ("balcony_dir", "n_open_sides", "view_type", "furnishing")
        }
        conn.execute(
            """INSERT INTO unit
               (unit_id, project_id, block, floor, total_floors, area_sqm, bedrooms, bathrooms,
                balcony_dir, n_open_sides, is_corner, view_type, furnishing, price_vnd, status,
                raw_description, canonical_text, provenance, source_url, is_synthetic, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                u["unit_id"], u["project_id"], u["block"] or None, u["floor"], u["total_floors"],
                u["area_sqm"], u["bedrooms"], u["bathrooms"], u["balcony_dir"] or None,
                u["n_open_sides"] or None, 1 if int(u["n_open_sides"] or 0) >= 2 else 0,
                u["view_type"] or None, u["furnishing"] or FURNISHING_DEFAULT.get(u["bedrooms"], "basic"),
                u["price_vnd"], u["status"],
                None,
                f"Căn {u['bedrooms']}PN, {u['area_sqm']}m², tầng {u['floor']}/{u['total_floors']}, "
                f"ban công {u['balcony_dir'] or 'chưa rõ'}.",
                json.dumps(provenance, ensure_ascii=False), None, 1, created_at,
            ),
        )

    # unit_business: dữ liệu nội bộ giả lập, dùng cho HITL console và kiểm chứng chống
    # thiên vị business_priority (xem tests/test_business_priority_isolation.py).
    rng = random.Random(42)
    for u in units:
        conn.execute(
            """INSERT INTO unit_business
               (unit_id, days_on_market, business_priority, discount_pct, commission_pct, policy_note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                u["unit_id"], rng.randint(5, 240), round(rng.uniform(0.2, 0.9), 2),
                round(rng.uniform(0, 5), 1), round(rng.uniform(1.5, 3.0), 1),
                None,
            ),
        )

    # project_poi_distance: tính sẵn bằng haversine, không cần PostGIS/pgvector.
    for p in projects:
        for poi_id, poi in zip(poi_ids, pois, strict=True):
            d = haversine_m(float(p["lat"]), float(p["lng"]), float(poi["lat"]), float(poi["lng"]))
            conn.execute(
                "INSERT INTO project_poi_distance (project_id, poi_id, distance_m) VALUES (?, ?, ?)",
                (p["project_id"], poi_id, round(d)),
            )

    # app_user: một tài khoản sale mock để gán vào session/audit_log (không có auth thật ở prototype).
    conn.execute(
        "INSERT INTO app_user (user_id, role, display_name, phone_masked, created_at) VALUES (1, 'sale', 'Sale demo', NULL, ?)",
        (created_at,),
    )

    conn.commit()

    n_dist = conn.execute("SELECT count(*) FROM project_poi_distance").fetchone()[0]
    n_units = conn.execute("SELECT count(*) FROM unit").fetchone()[0]
    print(f"Seeded {len(projects)} projects, {len(pois)} pois, {n_units} units, "
          f"{n_dist} project_poi_distance rows (expect {len(projects)}x{len(pois)}={len(projects) * len(pois)}).")
    conn.close()


if __name__ == "__main__":
    seed()

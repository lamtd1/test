"""retrieve(criteria, envelope) -> list[ScoredUnit]. Lọc cứng bằng SQL, chấm điểm bằng Python.
Cố tình KHÔNG nhận business_priority làm tham số — xem tests/test_business_priority_isolation.py.

balcony_dir / n_open_sides / view_type / furnishing có thể NULL (chưa biết — xem
docs/schemas.md). Thành phần nào NULL thì loại khỏi trung bình có trọng số khi chấm
điểm, không tính là 0 (docs/spec/retrieval-ranking.md)."""

import sqlite3
from dataclasses import dataclass, field

from src.models.criteria import CriteriaSchema
from src.models.envelop import Envelope

DIR_BONUS = {"S": 1.0, "SE": 1.0, "E": 0.85, "SW": 0.7, "N": 0.4, "NE": 0.6, "NW": 0.4, "W": 0.3}
DIR_VI = {
    "N": "Bắc", "S": "Nam", "E": "Đông", "W": "Tây",
    "SE": "Đông Nam", "SW": "Tây Nam", "NE": "Đông Bắc", "NW": "Tây Bắc",
}


@dataclass
class ScoredUnit:
    row: sqlite3.Row
    project_name: str
    match_score: float
    poi_distances: dict[str, float] = field(default_factory=dict)  # poi_name -> distance_m


def _near_poi_score(distance_m: float, ideal_m: float, max_m: float) -> float:
    if distance_m <= ideal_m:
        return 1.0
    if distance_m >= max_m:
        return 0.0
    return max(0.0, min(1.0, 1 - (distance_m - ideal_m) / (max_m - ideal_m)))


def _airiness_score(floor: int, total_floors: int, balcony_dir: str | None, n_open_sides: int | None) -> float:
    """floor_ratio luôn có (floor/total_floors không bao giờ NULL). dir_bonus và
    open_sides bị loại khỏi trung bình nếu field gốc NULL, weight còn lại renormalize."""
    floor_ratio = floor / total_floors if total_floors else 0
    components: list[tuple[float, float]] = [(0.4, floor_ratio)]  # (weight, value)
    if balcony_dir is not None:
        components.append((0.4, DIR_BONUS.get(balcony_dir, 0.5)))
    if n_open_sides is not None:
        components.append((0.2, n_open_sides / 3))
    weight_sum = sum(w for w, _ in components)
    return sum(w * v for w, v in components) / weight_sum


def _view_score(view_type: str | None, preferred: list[str]) -> float | None:
    if view_type is None:
        return None
    if not preferred:
        return 0.5
    if view_type not in preferred:
        return 0.0
    rank = preferred.index(view_type)
    return max(0.0, 1 - rank / len(preferred))


def _hard_filter_sql(criteria: CriteriaSchema, envelope: Envelope) -> tuple[str, list]:
    hc = criteria.hard_constraints
    clauses = ["u.status = 'available'"]
    params: list = []

    price_cap = hc.price_max_vnd or envelope.price_max_vnd
    clauses.append("u.price_vnd <= ?")
    params.append(price_cap)

    if hc.bedrooms_min:
        clauses.append("u.bedrooms >= ?")
        params.append(hc.bedrooms_min)
    if hc.bathrooms_min:
        clauses.append("u.bathrooms >= ?")
        params.append(hc.bathrooms_min)
    if hc.area_min_m2:
        clauses.append("u.area_sqm >= ?")
        params.append(hc.area_min_m2)
    if hc.floor_min:
        clauses.append("u.floor >= ?")
        params.append(hc.floor_min)
    if hc.district:
        placeholders = ",".join("?" for _ in hc.district)
        clauses.append(f"p.district IN ({placeholders})")
        params.extend(hc.district)

    for db in criteria.deal_breakers:
        if db.key == "balcony_dir" and db.op == "ne":
            clauses.append("u.balcony_dir IS NOT ?")
            params.append(db.value)
        elif db.key == "balcony_dir" and db.op == "eq":
            clauses.append("u.balcony_dir = ?")
            params.append(db.value)
        elif db.key == "handover_year" and db.op == "lte":
            # p.handover_date NULL = đã bàn giao -> luôn thoả "bàn giao trước năm X"
            clauses.append("(p.handover_date IS NULL OR CAST(strftime('%Y', p.handover_date) AS INTEGER) <= ?)")
            params.append(db.value)
        elif db.key == "handover_year" and db.op == "gte":
            clauses.append("(p.handover_date IS NOT NULL AND CAST(strftime('%Y', p.handover_date) AS INTEGER) >= ?)")
            params.append(db.value)

    sql = f"""SELECT u.*, p.name AS project_name, p.district AS district, p.handover_date AS handover_date
              FROM unit u JOIN project p ON p.project_id = u.project_id
              WHERE {' AND '.join(clauses)}"""
    return sql, params


def retrieve(criteria: CriteriaSchema, envelope: Envelope, conn: sqlite3.Connection) -> list[ScoredUnit]:
    sql, params = _hard_filter_sql(criteria, envelope)
    rows = conn.execute(sql, params).fetchall()

    scored: list[ScoredUnit] = []
    for row in rows:
        weighted_sum = 0.0
        weight_total = 0.0
        poi_distances: dict[str, float] = {}

        for pref in criteria.soft_preferences:
            weight = pref.weight * (0.7 if pref.confidence == "low" else 1.0)

            if pref.key == "near_poi":
                poi_id = pref.params.get("poi_id")
                if poi_id is None:
                    continue
                dist_row = conn.execute(
                    "SELECT d.distance_m, po.name FROM project_poi_distance d "
                    "JOIN poi po ON po.poi_id = d.poi_id "
                    "WHERE d.project_id = ? AND d.poi_id = ?",
                    (row["project_id"], poi_id),
                ).fetchone()
                if dist_row is None:
                    continue
                ideal = pref.params.get("ideal_m", 500)
                max_d = pref.params.get("max_m", 2000)
                score = _near_poi_score(dist_row["distance_m"], ideal, max_d)
                poi_distances[dist_row["name"]] = dist_row["distance_m"]

            elif pref.key == "airiness":
                score = _airiness_score(row["floor"], row["total_floors"], row["balcony_dir"], row["n_open_sides"])

            elif pref.key == "view":
                score = _view_score(row["view_type"], pref.params.get("preferred", []))
                if score is None:
                    continue

            else:
                continue

            weighted_sum += weight * score
            weight_total += weight

        match_score = weighted_sum / weight_total if weight_total > 0 else 0.5
        scored.append(ScoredUnit(
            row=row, project_name=row["project_name"], match_score=match_score, poi_distances=poi_distances,
        ))

    scored.sort(key=lambda s: s.match_score, reverse=True)
    return scored

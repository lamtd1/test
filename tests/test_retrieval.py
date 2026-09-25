import inspect

import pytest

from src.db import get_conn, init_schema
from src.models.criteria import CriteriaSchema, HardConstraints, SoftPreference
from src.models.envelop import Envelope
from src.services.explain import explain
from src.services.retrieval import retrieve


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import src.db as db_module

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    c = get_conn()
    init_schema(c)
    c.execute(
        "INSERT INTO project (project_id, name, district, lat, lng, geo_source, is_synthetic) "
        "VALUES ('proj-a', 'Proj A', 'Nam Từ Liêm', 21.0100, 105.7550, 'manual', 1)"
    )
    c.execute(
        "INSERT INTO poi (poi_id, type, name, lat, lng) VALUES (1, 'school_primary', 'Tiểu học Test', 21.0110, 105.7555)"
    )
    c.execute("INSERT INTO project_poi_distance (project_id, poi_id, distance_m) VALUES ('proj-a', 1, 300)")
    c.executemany(
        """INSERT INTO unit
           (unit_id, project_id, floor, total_floors, area_sqm, bedrooms, bathrooms,
            balcony_dir, n_open_sides, view_type, price_vnd, status, is_synthetic, created_at)
           VALUES (?, 'proj-a', ?, 30, ?, ?, 2, ?, ?, ?, ?, 'available', 1, '2026-01-01')""",
        [
            ("A-01", 10, 68, 2, "SE", 2, "park", 2_800_000_000),
            ("A-02", 5, 40, 1, "N", 1, "internal", 1_500_000_000),
            ("A-03", 12, 70, 2, "SE", 2, "park", 5_000_000_000),
        ],
    )
    c.execute("INSERT INTO unit_business (unit_id, business_priority, days_on_market) VALUES ('A-01', 0.9, 10)")
    c.execute("INSERT INTO unit_business (unit_id, business_priority, days_on_market) VALUES ('A-02', 0.5, 10)")
    c.execute("INSERT INTO unit_business (unit_id, business_priority, days_on_market) VALUES ('A-03', 0.5, 10)")
    c.commit()
    yield c
    c.close()


def _criteria() -> CriteriaSchema:
    return CriteriaSchema(
        hard_constraints=HardConstraints(bedrooms_min=2, price_max_vnd=3_000_000_000),
        soft_preferences=[
            SoftPreference(key="near_poi", params={"poi_id": 1, "ideal_m": 300, "max_m": 1000},
                            weight=1.0, confidence="high", source="user_stated", raw_quote="gần trường"),
        ],
    )


def _envelope() -> Envelope:
    return Envelope(
        price_min_vnd=2_500_000_000, price_max_vnd=3_000_000_000, price_target_vnd=2_750_000_000,
        installment_promo_vnd=15_000_000, installment_float_vnd=18_000_000,
        binding_constraint="capacity", income_bucket="50-60tr", scenarios=[],
        disclaimer="test",
    )


def test_hard_filters_exclude_wrong_bedrooms_and_over_budget(conn):
    scored = retrieve(_criteria(), _envelope(), conn)
    codes = {s.row["unit_id"] for s in scored}
    assert codes == {"A-01"}  # A-02 sai bedrooms, A-03 vượt price_max


def test_match_score_does_not_accept_business_priority():
    params = inspect.signature(retrieve).parameters
    assert "business_priority" not in params


def test_explain_always_returns_at_least_one_tradeoff(conn):
    scored = retrieve(_criteria(), _envelope(), conn)
    reasons, tradeoffs = explain(scored[0], _criteria(), _envelope())
    assert len(reasons) >= 1
    assert len(tradeoffs) >= 1


def test_airiness_score_ignores_null_fields(conn):
    conn.execute(
        """INSERT INTO unit
           (unit_id, project_id, floor, total_floors, area_sqm, bedrooms, bathrooms,
            balcony_dir, n_open_sides, view_type, price_vnd, status, is_synthetic, created_at)
           VALUES ('A-04', 'proj-a', 10, 30, 68, 2, 2, NULL, NULL, NULL, 2600000000, 'available', 1, '2026-01-01')"""
    )
    conn.execute("INSERT INTO unit_business (unit_id, business_priority, days_on_market) VALUES ('A-04', 0.5, 10)")
    conn.commit()

    criteria = CriteriaSchema(
        hard_constraints=HardConstraints(bedrooms_min=2, price_max_vnd=3_000_000_000),
        soft_preferences=[
            SoftPreference(key="airiness", params={}, weight=1.0, confidence="high",
                            source="agent_inferred", raw_quote=None),
        ],
    )
    scored = retrieve(criteria, _envelope(), conn)
    a04 = next(s for s in scored if s.row["unit_id"] == "A-04")
    assert 0 <= a04.match_score <= 1

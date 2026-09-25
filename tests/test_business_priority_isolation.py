"""match_score/shortlist khách phải mù hoàn toàn với business_priority (xem
docs/prototype-plan.md Bước 3 và README 'Hai điểm số tách biệt để chống thiên vị căn tồn').

Discovery agent bị buộc dùng nhánh fallback regex (không gọi Gemini thật) để test
nhanh, xác định và không tốn quota — xem docs/spec/discovery-agent.md."""

from starlette.testclient import TestClient

from src.models.shortlist import RankedUnit


def test_ranked_unit_schema_has_no_business_fields():
    assert "business_priority" not in RankedUnit.model_fields
    assert "days_on_market" not in RankedUnit.model_fields
    assert "commission_pct" not in RankedUnit.model_fields


def test_customer_shortlist_endpoint_never_returns_business_priority(tmp_path, monkeypatch):
    import src.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("GOOGLE_API_KEY", "")

    from scripts.seed import seed
    seed()

    import src.config as config_module
    config_module.settings = config_module.Settings()

    from src.main import app

    client = TestClient(app)

    session_id = client.post("/api/v1/sessions").json()["session_id"]
    client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"text": "Mình muốn căn 2 phòng ngủ gần trường tiểu học Nam Từ Liêm, thoáng một chút."},
    )
    client.post(
        f"/api/v1/sessions/{session_id}/finance",
        json={
            "cash_available_vnd": 1_200_000_000, "income_monthly_vnd": 60_000_000,
            "existing_debt_monthly_vnd": 3_000_000, "loan_term_years": 25,
        },
    )
    client.post(f"/api/v1/sessions/{session_id}/approve")

    body = client.get(f"/api/v1/sessions/{session_id}/shortlist").json()
    assert body["state"] == "sent"
    raw_text = str(body)
    assert "business_priority" not in raw_text
    assert "days_on_market" not in raw_text

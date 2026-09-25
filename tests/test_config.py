"""CORS_ORIGINS env var parsing — xem docs/superpowers/specs/2026-09-25-cicd-render-vercel-design.md."""

from src.config import Settings, parse_cors_origins


def test_parse_cors_origins_defaults_when_unset():
    assert parse_cors_origins(None) == [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


def test_parse_cors_origins_defaults_when_empty():
    assert parse_cors_origins("") == [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]


def test_parse_cors_origins_splits_and_strips():
    raw = "https://homematch.vercel.app, https://homematch-git-main.vercel.app"
    assert parse_cors_origins(raw) == [
        "https://homematch.vercel.app",
        "https://homematch-git-main.vercel.app",
    ]


def test_parse_cors_origins_strips_trailing_slash():
    assert parse_cors_origins("https://homematch.vercel.app/") == [
        "https://homematch.vercel.app",
    ]


def test_settings_reads_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    settings = Settings()
    assert settings.cors_origins == ["https://example.com"]


def test_settings_reads_cors_origin_regex_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"^https://test-.*\.vercel\.app$")
    settings = Settings()
    assert settings.cors_origin_regex == r"^https://test-.*\.vercel\.app$"


def test_settings_cors_origin_regex_defaults_to_none(monkeypatch):
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    settings = Settings()
    assert settings.cors_origin_regex is None

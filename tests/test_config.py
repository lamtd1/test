"""CORS_ORIGINS env var parsing — xem docs/superpowers/specs/2026-09-25-cicd-render-vercel-design.md."""

from src.config import parse_cors_origins


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

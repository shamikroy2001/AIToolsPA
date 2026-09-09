"""D1 staging freeze helpers. No live cloud calls."""

from app.core.dsn import (
    cors_allowlist,
    needs_ssl,
    parse_cors_origins,
    to_async_sqlalchemy,
    to_sync_psycopg,
    with_required_ssl,
)
from app.core.settings import Settings, clear_settings_cache


def test_supabase_postgres_url_becomes_asyncpg():
    raw = "postgres://postgres:secret@db.example.supabase.co:5432/postgres"
    assert to_async_sqlalchemy(raw) == (
        "postgresql+asyncpg://postgres:secret@db.example.supabase.co:5432/postgres"
    )
    assert to_sync_psycopg(raw).startswith("postgresql+psycopg://")
    assert needs_ssl(to_async_sqlalchemy(raw))
    assert "sslmode=require" in with_required_ssl(to_sync_psycopg(raw))


def test_local_docker_url_skips_ssl():
    url = "postgresql+asyncpg://pa_app:pa_app@postgres:5432/personal_assistant"
    assert needs_ssl(url) is False
    assert with_required_ssl(url) == url


def test_cors_accepts_comma_list_and_public_app():
    assert parse_cors_origins("https://app.example.com, https://other.example.com") == [
        "https://app.example.com",
        "https://other.example.com",
    ]
    assert cors_allowlist("https://app.example.com/", "https://app.example.com") == [
        "https://app.example.com"
    ]


def test_settings_merges_public_app_url(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://pa-staging.vercel.app")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://pa-staging.vercel.app")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://pa_app:x@db.example.supabase.co:5432/postgres",
    )
    monkeypatch.setenv(
        "DATABASE_ADMIN_URL",
        "postgresql://postgres:x@db.example.supabase.co:5432/postgres",
    )
    clear_settings_cache()
    settings = Settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.cors_origin_list() == ["https://pa-staging.vercel.app"]
    clear_settings_cache()

"""D1 staging freeze helpers. No live cloud calls."""

from sqlalchemy.engine.url import make_url

from app.core.db import engine_connect_args
from app.core.schema import missing_relation
from app.core.dsn import (
    cors_allowlist,
    describe_database_url,
    needs_ssl,
    parse_cors_origins,
    sanitize_database_url,
    sync_connect_args,
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


def test_remote_engine_always_sets_connect_timeout():
    args = engine_connect_args(
        "postgresql+asyncpg://pa_app:x@db.example.supabase.co:5432/postgres"
    )
    assert args["timeout"] == 15
    assert args["command_timeout"] == 15
    assert args["ssl"] == "require"


def test_supabase_hosts_use_require_ssl():
    pooler = engine_connect_args(
        "postgresql+asyncpg://postgres.proj:x@aws-0-ca-central-1.pooler.supabase.com:5432/postgres"
    )
    direct = engine_connect_args(
        "postgresql+asyncpg://postgres:x@db.example.supabase.co:5432/postgres"
    )
    assert pooler["ssl"] == "require"
    assert direct["ssl"] == "require"


def test_missing_relation_detects_undefined_table():
    assert missing_relation(Exception('relation "plans" does not exist'))
    assert missing_relation(Exception("asyncpg.exceptions.UndefinedTableError"))
    assert missing_relation(Exception("connection refused")) is False


def test_alembic_sync_args_only_set_timeout():
    args = sync_connect_args(
        "postgresql+psycopg://postgres.proj:x@aws-0-ca-central-1.pooler.supabase.com:5432/postgres"
    )
    assert args == {"connect_timeout": 15}


def test_password_at_sign_is_encoded_for_sqlalchemy():
    raw = (
        "postgresql+asyncpg://postgres.projref:Secret@Pass"
        "@aws-0-ca-central-1.pooler.supabase.com:5432/postgres"
    )
    out = to_async_sqlalchemy(raw)
    parsed = make_url(out)
    assert parsed.password == "Secret@Pass"
    assert parsed.host == "aws-0-ca-central-1.pooler.supabase.com"
    assert parsed.username == "postgres.projref"


def test_already_encoded_password_is_not_double_encoded():
    raw = (
        "postgresql+asyncpg://pa_app.projref:Secret%40Pass"
        "@aws-0-ca-central-1.pooler.supabase.com:5432/postgres"
    )
    out = to_async_sqlalchemy(raw)
    assert out.count("%40") == 1
    assert make_url(out).password == "Secret@Pass"


def test_describe_database_url_omits_password():
    summary = describe_database_url(
        "postgresql+asyncpg://pa_app:super-secret@aws-0-ca-central-1.pooler.supabase.com:5432/postgres"
    )
    assert "super-secret" not in summary
    assert "at_count=1" in summary
    assert "postgresql+asyncpg" in summary


def test_quoted_database_url_is_stripped():
    raw = '"postgresql://pa_app:x@localhost:5432/postgres"'
    assert sanitize_database_url(raw).startswith("postgresql://pa_app:")


def test_local_engine_sets_timeout_without_ssl():
    args = engine_connect_args(
        "postgresql+asyncpg://pa_app:pa_app@postgres:5432/personal_assistant"
    )
    assert args["timeout"] == 15
    assert "ssl" not in args

"""Normalize DSNs and CORS for Railway / Supabase / Vercel env vars."""

from __future__ import annotations

import json
import ssl
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse


def parse_cors_origins(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).rstrip("/") for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        loaded = json.loads(text)
        return [str(item).rstrip("/") for item in loaded if str(item).strip()]
    return [part.strip().rstrip("/") for part in text.split(",") if part.strip()]


def cors_allowlist(*origins: str) -> list[str]:
    seen: list[str] = []
    for origin in origins:
        cleaned = origin.strip().rstrip("/")
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def describe_database_url(url: str) -> str:
    """Safe-for-logs summary. Never includes the password."""
    raw = url or ""
    preview = raw[:28].replace("\n", "\\n").replace("\r", "\\r")
    scheme = raw.split("://", 1)[0] if "://" in raw else "none"
    return (
        f"len={len(raw)} at_count={raw.count('@')} scheme={scheme!r} preview={preview!r}"
    )


def sanitize_database_url(url: str) -> str:
    """Strip quotes and encode `@ : / #` in the password so SQLAlchemy can parse it.

    Railway often stores `P@ss` or decodes `%40` back to `@`, which otherwise
    makes the host look like `ss@aws-0-….pooler.supabase.com`.
    """
    url = (url or "").strip().strip('"').strip("'")
    if not url or url.startswith("sqlite") or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest or ":" not in rest.split("@", 1)[0]:
        return f"{scheme}://{rest}"
    userinfo, hostpart = rest.rsplit("@", 1)
    user, password = userinfo.split(":", 1)
    encoded = quote(unquote(password), safe="")
    return f"{scheme}://{user}:{encoded}@{hostpart}"


def to_async_sqlalchemy(url: str) -> str:
    url = sanitize_database_url(url)
    if not url or url.startswith("sqlite"):
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    return url


def to_sync_psycopg(url: str) -> str:
    url = url.strip()
    if not url or url.startswith("sqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    url = to_async_sqlalchemy(url)
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def _is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in {"localhost", "127.0.0.1", "postgres", "redis"}


def needs_ssl(url: str) -> bool:
    return bool(url) and not url.startswith("sqlite") and not _is_local(url)


def is_supabase_pooler(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith(".pooler.supabase.com")


def postgres_ssl_setting(url: str) -> bool | ssl.SSLContext:
    """asyncpg TLS. Pooler chains often fail default verify (self-signed intermediate)."""
    if is_supabase_pooler(url):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return True


def with_required_ssl(url: str) -> str:
    if not needs_ssl(url):
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "ssl" not in query and "sslmode" not in query:
        query["sslmode"] = "require"
    return urlunparse(parsed._replace(query=urlencode(query)))

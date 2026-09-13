"""Supabase Data API (publishable / secret keys). Not a replacement for SQLAlchemy."""

from __future__ import annotations

import time

import httpx

from app.core.settings import Settings, get_settings

_PROBE_TTL_SECONDS = 30.0
_probe_cache: tuple[float, str] | None = None


def supabase_api_key(settings: Settings) -> str | None:
    for raw in (
        settings.supabase_secret_key,
        settings.supabase_publishable_key,
    ):
        key = (raw or "").strip()
        if key:
            return key
    return None


def supabase_api_url(settings: Settings) -> str | None:
    url = (settings.supabase_url or "").strip().rstrip("/")
    return url or None


def probe_supabase(settings: Settings | None = None) -> str:
    """Return ok, unconfigured, or error. New keys go on the apikey header only."""
    global _probe_cache
    now = time.monotonic()
    if _probe_cache and now - _probe_cache[0] < _PROBE_TTL_SECONDS:
        return _probe_cache[1]

    settings = settings or get_settings()
    url = supabase_api_url(settings)
    key = supabase_api_key(settings)
    if not url or not key:
        status = "unconfigured"
    else:
        try:
            response = httpx.get(
                f"{url}/rest/v1/",
                headers={"apikey": key, "Accept": "application/json"},
                timeout=5.0,
            )
            status = "ok" if response.status_code < 400 else "error"
        except httpx.HTTPError:
            status = "error"

    _probe_cache = (now, status)
    return status


def clear_supabase_probe_cache() -> None:
    global _probe_cache
    _probe_cache = None

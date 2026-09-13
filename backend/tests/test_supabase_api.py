from types import SimpleNamespace

import httpx

from app.core.settings import Settings, clear_settings_cache
from app.core.supabase_api import (
    clear_supabase_probe_cache,
    probe_supabase,
    supabase_api_key,
    supabase_api_url,
)


def test_reads_new_api_key_names(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    clear_settings_cache()
    settings = Settings()
    assert supabase_api_url(settings) == "https://proj.supabase.co"
    assert supabase_api_key(settings) == "sb_secret_test"
    clear_settings_cache()


def test_accepts_connect_dialog_next_public_names(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://proj.supabase.co/")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    clear_settings_cache()
    settings = Settings()
    assert supabase_api_url(settings) == "https://proj.supabase.co"
    assert supabase_api_key(settings) == "sb_publishable_test"
    clear_settings_cache()


def test_probe_unconfigured_without_keys():
    clear_supabase_probe_cache()
    status = probe_supabase(
        SimpleNamespace(supabase_url=None, supabase_publishable_key=None, supabase_secret_key=None)
    )
    assert status == "unconfigured"


def test_probe_ok_uses_apikey_header_only(monkeypatch):
    clear_supabase_probe_cache()

    def fake_get(url, headers, timeout):
        assert url == "https://proj.supabase.co/rest/v1/"
        assert headers["apikey"] == "sb_publishable_test"
        assert "Authorization" not in headers
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.core.supabase_api.httpx.get", fake_get)
    status = probe_supabase(
        SimpleNamespace(
            supabase_url="https://proj.supabase.co",
            supabase_publishable_key="sb_publishable_test",
            supabase_secret_key=None,
        )
    )
    assert status == "ok"


def test_legacy_service_role_alias(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-service-role")
    clear_settings_cache()
    settings = Settings()
    assert supabase_api_key(settings) == "legacy-service-role"
    clear_settings_cache()

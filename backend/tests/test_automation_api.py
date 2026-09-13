"""Automation catalog, monitors, schedules, notifications. No live Gmail/Telegram."""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.db import admin_session_factory
from app.core.settings import clear_settings_cache
from app.models.automation import Notification
from app.workers.arq_worker import poll_due_monitors
from conftest import TOKEN_A, TOKEN_B


def _auth(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_no_secrets(payload: object) -> None:
    text = str(payload).lower()
    for forbidden in (
        "encrypted_credentials",
        "refresh_token",
        "access_token",
        "client_secret",
        "bot_token",
        "gmail_client",
        "telegram_bot",
    ):
        assert forbidden not in text


def test_catalog_lists_providers_without_tokens(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.get("/api/integrations", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert {row["provider"] for row in body} == {"gmail", "telegram"}
    assert all(row["status"] == "disconnected" for row in body)
    _assert_no_secrets(body)


def test_gmail_connect_without_env_is_503(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/integrations/gmail/connect", headers=_auth())
    assert response.status_code == 503
    assert "gmail" in response.json()["detail"].lower()
    _assert_no_secrets(response.json())


def test_telegram_connect_without_env_is_503(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/integrations/telegram/connect", headers=_auth())
    assert response.status_code == 503
    assert "telegram" in response.json()["detail"].lower()
    _assert_no_secrets(response.json())


def test_gmail_connect_with_env_still_does_not_return_tokens(
    saas_client: TestClient, monkeypatch
):
    monkeypatch.setenv("GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "client-secret")
    clear_settings_cache()
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/integrations/gmail/connect", headers=_auth())
    assert response.status_code == 503
    _assert_no_secrets(response.json())
    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    clear_settings_cache()


def test_unknown_integration_is_404(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/integrations/slack/connect", headers=_auth())
    assert response.status_code == 404


def test_automation_routes_require_auth(saas_client: TestClient):
    assert saas_client.get("/api/integrations").status_code == 401
    assert saas_client.get("/api/monitors").status_code == 401
    assert saas_client.get("/api/schedules").status_code == 401
    assert saas_client.get("/api/notifications").status_code == 401


def test_monitor_crud_and_isolation(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth(TOKEN_A))
    saas_client.get("/api/me", headers=_auth(TOKEN_B))
    created = saas_client.post(
        "/api/monitors",
        json={"url": "https://example.com/status"},
        headers=_auth(TOKEN_A),
    )
    assert created.status_code == 200
    body = created.json()
    assert body["url"] == "https://example.com/status"
    assert body["enabled"] is True
    assert "last_hash" not in body
    _assert_no_secrets(body)

    denied = saas_client.get(f"/api/monitors/{body['id']}", headers=_auth(TOKEN_B))
    assert denied.status_code == 404
    assert saas_client.get("/api/monitors", headers=_auth(TOKEN_B)).json() == []
    assert (
        saas_client.patch(
            f"/api/monitors/{body['id']}",
            json={"enabled": False},
            headers=_auth(TOKEN_B),
        ).status_code
        == 404
    )
    assert (
        saas_client.delete(f"/api/monitors/{body['id']}", headers=_auth(TOKEN_B)).status_code
        == 404
    )

    patched = saas_client.patch(
        f"/api/monitors/{body['id']}",
        json={"enabled": False},
        headers=_auth(TOKEN_A),
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    listed = saas_client.get("/api/monitors", headers=_auth(TOKEN_A)).json()
    assert listed[0]["id"] == body["id"]

    deleted = saas_client.delete(f"/api/monitors/{body['id']}", headers=_auth(TOKEN_A))
    assert deleted.status_code == 204
    assert saas_client.get("/api/monitors", headers=_auth(TOKEN_A)).json() == []


def test_monitor_rejects_non_http_url(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post(
        "/api/monitors",
        json={"url": "javascript:alert(1)"},
        headers=_auth(),
    )
    assert response.status_code == 422


def test_schedule_crud_and_isolation(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth(TOKEN_A))
    saas_client.get("/api/me", headers=_auth(TOKEN_B))
    created = saas_client.post(
        "/api/schedules",
        json={"task_type": "website_monitor", "cadence": "daily", "payload": {"note": "home"}},
        headers=_auth(TOKEN_A),
    )
    assert created.status_code == 200
    body = created.json()
    assert body["task_type"] == "website_monitor"
    assert body["cadence"] == "daily"
    assert body["payload"] == {"note": "home"}
    assert body["next_run_at"] is not None
    _assert_no_secrets(body)

    denied = saas_client.get(f"/api/schedules/{body['id']}", headers=_auth(TOKEN_B))
    assert denied.status_code == 404
    assert saas_client.get("/api/schedules", headers=_auth(TOKEN_B)).json() == []
    assert (
        saas_client.patch(
            f"/api/schedules/{body['id']}",
            json={"enabled": False},
            headers=_auth(TOKEN_B),
        ).status_code
        == 404
    )
    assert (
        saas_client.delete(f"/api/schedules/{body['id']}", headers=_auth(TOKEN_B)).status_code
        == 404
    )

    patched = saas_client.patch(
        f"/api/schedules/{body['id']}",
        json={"cadence": "weekly", "enabled": False},
        headers=_auth(TOKEN_A),
    )
    assert patched.status_code == 200
    assert patched.json()["cadence"] == "weekly"
    assert patched.json()["enabled"] is False

    deleted = saas_client.delete(f"/api/schedules/{body['id']}", headers=_auth(TOKEN_A))
    assert deleted.status_code == 204
    assert saas_client.get("/api/schedules", headers=_auth(TOKEN_A)).json() == []


def test_schedule_rejects_secret_payload_and_unknown_type(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    secrets = saas_client.post(
        "/api/schedules",
        json={"task_type": "website_monitor", "payload": {"refresh_token": "abc"}},
        headers=_auth(),
    )
    assert secrets.status_code == 422
    unknown = saas_client.post(
        "/api/schedules",
        json={"task_type": "launch_missiles", "cadence": "daily"},
        headers=_auth(),
    )
    assert unknown.status_code == 422


def test_notifications_are_tenant_scoped(saas_client: TestClient):
    me_a = saas_client.get("/api/me", headers=_auth(TOKEN_A)).json()
    me_b = saas_client.get("/api/me", headers=_auth(TOKEN_B)).json()

    async def _seed() -> None:
        factory = admin_session_factory()
        async with factory() as session:
            session.add(
                Notification(
                    user_id=UUID(me_a["id"]),
                    title="Only A",
                    body="private",
                    channel="in_app",
                )
            )
            session.add(
                Notification(
                    user_id=UUID(me_b["id"]),
                    title="Only B",
                    body="private",
                    channel="in_app",
                )
            )
            await session.commit()

    asyncio.run(_seed())

    listed_a = saas_client.get("/api/notifications", headers=_auth(TOKEN_A)).json()
    listed_b = saas_client.get("/api/notifications", headers=_auth(TOKEN_B)).json()
    assert [row["title"] for row in listed_a] == ["Only A"]
    assert [row["title"] for row in listed_b] == ["Only B"]
    _assert_no_secrets(listed_a)


def test_poll_due_monitors_is_noop_without_secrets():
    assert asyncio.run(poll_due_monitors({})) == 0

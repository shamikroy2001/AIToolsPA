"""Gmail OAuth + Telegram connect. Public JSON must never include secrets."""

from __future__ import annotations

import asyncio
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.core.crypto import decrypt_json, encrypt_secret
from app.core.db import admin_session_factory
from app.core.settings import clear_settings_cache
from app.models.automation import Integration
from app.services.gmail import GmailService, encode_oauth_state
from app.services.telegram import TelegramService
from conftest import TOKEN_A, TOKEN_B

MOCK_ACCESS = "ya29.mock-access-token"
MOCK_REFRESH = "1//mock-refresh-token"
MOCK_EMAIL = "reader@example.com"
MOCK_BOT = "111111:AA-test-bot-secret"
MOCK_CHAT = "42424242"


def _auth(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_no_secrets(payload: object, *extra: str) -> None:
    text = str(payload).lower()
    for forbidden in (
        "encrypted_credentials",
        "refresh_token",
        "access_token",
        "client_secret",
        "bot_token",
        "gmail_client",
        "telegram_bot",
        MOCK_ACCESS.lower(),
        MOCK_REFRESH.lower(),
        MOCK_BOT.lower(),
        "aa-test-bot-secret",
        *extra,
    ):
        assert forbidden not in text


def _enable_gmail(monkeypatch) -> None:
    monkeypatch.setenv("GMAIL_CLIENT_ID", "client-id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    clear_settings_cache()


def _enable_telegram(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", MOCK_BOT)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    clear_settings_cache()


def _user_id(saas_client: TestClient, token: str = TOKEN_A) -> UUID:
    return UUID(saas_client.get("/api/me", headers=_auth(token)).json()["id"])


async def _integration_row(user_id: UUID, provider: str) -> Integration | None:
    factory = admin_session_factory()
    async with factory() as session:
        return await session.scalar(
            select(Integration)
            .options(undefer(Integration.encrypted_credentials))
            .where(Integration.user_id == user_id, Integration.provider == provider)
        )


def test_encrypt_secret_roundtrip_is_not_plaintext(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    clear_settings_cache()
    cipher = encrypt_secret(MOCK_REFRESH)
    assert MOCK_REFRESH not in cipher
    assert decrypt_json(encrypt_secret('{"refresh_token":"%s"}' % MOCK_REFRESH))[
        "refresh_token"
    ] == MOCK_REFRESH
    clear_settings_cache()


def test_gmail_connect_without_env_is_503(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/integrations/gmail/connect", headers=_auth())
    assert response.status_code == 503
    assert "gmail" in response.json()["detail"].lower()
    _assert_no_secrets(response.json())


def test_telegram_connect_without_env_is_503(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post(
        "/api/integrations/telegram/connect",
        json={"chat_id": MOCK_CHAT},
        headers=_auth(),
    )
    assert response.status_code == 503
    assert "telegram" in response.json()["detail"].lower()
    _assert_no_secrets(response.json())


def test_gmail_mocked_oauth_persists_encrypted_credentials(
    saas_client: TestClient, monkeypatch
):
    _enable_gmail(monkeypatch)
    user_id = _user_id(saas_client)

    async def fake_exchange(self, code: str, *, redirect_uri: str) -> dict:
        assert code == "auth-code"
        assert redirect_uri.endswith("/api/integrations/gmail/callback")
        return {
            "access_token": MOCK_ACCESS,
            "refresh_token": MOCK_REFRESH,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
            "email": MOCK_EMAIL,
        }

    monkeypatch.setattr(GmailService, "exchange_code", fake_exchange)

    start = saas_client.post("/api/integrations/gmail/connect", headers=_auth())
    assert start.status_code == 200
    authorize_url = start.json()["authorize_url"]
    assert "gmail.readonly" in authorize_url
    assert "gmail.send" not in authorize_url
    _assert_no_secrets(start.json())

    state = encode_oauth_state(user_id)
    completed = saas_client.post(
        "/api/integrations/gmail/connect",
        json={"code": "auth-code", "state": state},
        headers=_auth(),
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "connected"
    assert body["account_label"] == MOCK_EMAIL
    assert body.get("authorize_url") in (None, "")
    _assert_no_secrets(body)

    catalog = saas_client.get("/api/integrations", headers=_auth()).json()
    gmail = next(row for row in catalog if row["provider"] == "gmail")
    assert gmail["status"] == "connected"
    assert gmail["account_label"] == MOCK_EMAIL
    _assert_no_secrets(catalog)

    row = asyncio.run(_integration_row(user_id, "gmail"))
    assert row is not None
    assert row.status == "connected"
    assert row.encrypted_credentials
    assert MOCK_ACCESS not in row.encrypted_credentials
    assert MOCK_REFRESH not in row.encrypted_credentials
    stored = decrypt_json(row.encrypted_credentials)
    assert stored["refresh_token"] == MOCK_REFRESH
    assert stored["access_token"] == MOCK_ACCESS

    saas_client.get("/api/me", headers=_auth(TOKEN_B))
    other = saas_client.get("/api/integrations", headers=_auth(TOKEN_B)).json()
    other_gmail = next(row for row in other if row["provider"] == "gmail")
    assert other_gmail["status"] == "disconnected"
    assert other_gmail.get("account_label") in (None, "")
    _assert_no_secrets(other)

    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    clear_settings_cache()


def test_gmail_callback_persists_and_redirects_without_secrets(
    saas_client: TestClient, monkeypatch
):
    _enable_gmail(monkeypatch)
    user_id = _user_id(saas_client)

    async def fake_exchange(self, code: str, *, redirect_uri: str) -> dict:
        del redirect_uri
        assert code == "cb-code"
        return {
            "access_token": MOCK_ACCESS,
            "refresh_token": MOCK_REFRESH,
            "token_type": "Bearer",
            "email": MOCK_EMAIL,
        }

    monkeypatch.setattr(GmailService, "exchange_code", fake_exchange)
    state = encode_oauth_state(user_id)
    response = saas_client.get(
        f"/api/integrations/gmail/callback?code=cb-code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.endswith("/integrations?gmail=connected")
    _assert_no_secrets(location)
    _assert_no_secrets(dict(response.headers))

    catalog = saas_client.get("/api/integrations", headers=_auth()).json()
    gmail = next(row for row in catalog if row["provider"] == "gmail")
    assert gmail["status"] == "connected"
    _assert_no_secrets(catalog)

    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    clear_settings_cache()


def test_gmail_disconnect_revokes_and_clears(saas_client: TestClient, monkeypatch):
    _enable_gmail(monkeypatch)
    user_id = _user_id(saas_client)
    revoked: list[str] = []

    async def fake_exchange(self, code: str, *, redirect_uri: str) -> dict:
        del self, code, redirect_uri
        return {
            "access_token": MOCK_ACCESS,
            "refresh_token": MOCK_REFRESH,
            "email": MOCK_EMAIL,
        }

    async def fake_revoke(self, token: str) -> None:
        del self
        revoked.append(token)

    monkeypatch.setattr(GmailService, "exchange_code", fake_exchange)
    monkeypatch.setattr(GmailService, "revoke", fake_revoke)
    state = encode_oauth_state(user_id)
    assert (
        saas_client.post(
            "/api/integrations/gmail/connect",
            json={"code": "auth-code", "state": state},
            headers=_auth(),
        ).status_code
        == 200
    )

    response = saas_client.post("/api/integrations/gmail/disconnect", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"
    assert body.get("account_label") in (None, "")
    _assert_no_secrets(body)
    assert revoked == [MOCK_REFRESH]

    row = asyncio.run(_integration_row(user_id, "gmail"))
    assert row is not None
    assert row.status == "disconnected"
    assert row.encrypted_credentials == ""

    catalog = saas_client.get("/api/integrations", headers=_auth()).json()
    gmail = next(item for item in catalog if item["provider"] == "gmail")
    assert gmail["status"] == "disconnected"
    _assert_no_secrets(catalog)

    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    clear_settings_cache()


def test_telegram_connect_with_env_requires_chat_id(saas_client: TestClient, monkeypatch):
    _enable_telegram(monkeypatch)
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/integrations/telegram/connect", headers=_auth())
    assert response.status_code == 400
    assert "chat" in response.json()["detail"].lower()
    _assert_no_secrets(response.json())
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    clear_settings_cache()


def test_telegram_rejects_bot_token_as_chat_id(saas_client: TestClient, monkeypatch):
    _enable_telegram(monkeypatch)
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post(
        "/api/integrations/telegram/connect",
        json={"chat_id": MOCK_BOT},
        headers=_auth(),
    )
    assert response.status_code == 400
    _assert_no_secrets(response.json())
    extra = saas_client.post(
        "/api/integrations/telegram/connect",
        json={"bot_token": MOCK_BOT},
        headers=_auth(),
    )
    assert extra.status_code == 400
    assert "credential" in extra.json()["detail"].lower()
    _assert_no_secrets(extra.json())
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    clear_settings_cache()


def test_telegram_mocked_connect_persists_encrypted_chat_and_disconnects(
    saas_client: TestClient, monkeypatch
):
    _enable_telegram(monkeypatch)
    user_id = _user_id(saas_client)
    saas_client.get("/api/me", headers=_auth(TOKEN_B))

    async def fake_verify(self, chat_id: str) -> dict:
        del self
        assert chat_id == MOCK_CHAT
        return {"chat_id": MOCK_CHAT, "username": "alice"}

    monkeypatch.setattr(TelegramService, "verify_chat", fake_verify)
    response = saas_client.post(
        "/api/integrations/telegram/connect",
        json={"chat_id": MOCK_CHAT},
        headers=_auth(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["account_label"] == "@alice"
    _assert_no_secrets(body, MOCK_CHAT)

    catalog = saas_client.get("/api/integrations", headers=_auth()).json()
    telegram = next(row for row in catalog if row["provider"] == "telegram")
    assert telegram["status"] == "connected"
    _assert_no_secrets(catalog, MOCK_CHAT)

    row = asyncio.run(_integration_row(user_id, "telegram"))
    assert row is not None
    assert row.status == "connected"
    assert MOCK_CHAT not in row.encrypted_credentials
    assert MOCK_BOT not in row.encrypted_credentials
    stored = decrypt_json(row.encrypted_credentials)
    assert stored["chat_id"] == MOCK_CHAT
    assert "bot_token" not in stored

    isolated = saas_client.get("/api/integrations", headers=_auth(TOKEN_B)).json()
    other = next(row for row in isolated if row["provider"] == "telegram")
    assert other["status"] == "disconnected"
    _assert_no_secrets(isolated, MOCK_CHAT)

    disconnected = saas_client.post(
        "/api/integrations/telegram/disconnect", headers=_auth()
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "disconnected"
    _assert_no_secrets(disconnected.json(), MOCK_CHAT)
    cleared = asyncio.run(_integration_row(user_id, "telegram"))
    assert cleared is not None
    assert cleared.encrypted_credentials == ""

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    clear_settings_cache()

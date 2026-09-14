"""Gmail OAuth (read-only). Tokens stay on the server; never returned to clients."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import Request

from app.core.crypto import decrypt_json, encrypt_json
from app.core.settings import get_settings

log = logging.getLogger("app.gmail")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Read/summarize mail only. Do not add send or modify scopes.
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
)

STATE_MAX_AGE_SECONDS = 600
HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class GmailOAuthError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def gmail_configured() -> bool:
    settings = get_settings()
    return bool(settings.gmail_client_id and settings.gmail_client_secret)


def gmail_redirect_uri(request: Request | None = None) -> str:
    settings = get_settings()
    if settings.gmail_redirect_uri:
        return settings.gmail_redirect_uri.rstrip("/")
    if settings.public_api_url:
        return f"{settings.public_api_url.rstrip('/')}/api/integrations/gmail/callback"
    if request is not None:
        return str(request.base_url).rstrip("/") + "/api/integrations/gmail/callback"
    raise GmailOAuthError("Gmail redirect URL is not configured.")


def encode_oauth_state(user_id: UUID, provider: str = "gmail") -> str:
    return encrypt_json(
        {
            "uid": str(user_id),
            "p": provider,
            "ts": int(time.time()),
        }
    )


def decode_oauth_state(state: str, *, expected_user_id: UUID | None = None) -> UUID:
    try:
        data = decrypt_json(state)
    except Exception as exc:
        raise GmailOAuthError("Gmail authorization state is invalid.") from exc
    try:
        stamped = int(data.get("ts") or 0)
    except (TypeError, ValueError) as exc:
        raise GmailOAuthError("Gmail authorization state is invalid.") from exc
    if stamped <= 0 or int(time.time()) - stamped > STATE_MAX_AGE_SECONDS:
        raise GmailOAuthError("Gmail authorization expired. Try connecting again.")
    if data.get("p") != "gmail":
        raise GmailOAuthError("Gmail authorization state is invalid.")
    raw_uid = data.get("uid")
    try:
        user_id = UUID(str(raw_uid))
    except (TypeError, ValueError) as exc:
        raise GmailOAuthError("Gmail authorization state is invalid.") from exc
    if expected_user_id is not None and user_id != expected_user_id:
        raise GmailOAuthError("Gmail authorization state is invalid.")
    return user_id


class GmailService:
    scopes = GMAIL_SCOPES

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        settings = get_settings()
        if not settings.gmail_client_id or not settings.gmail_client_secret:
            raise GmailOAuthError("Gmail connection is not configured yet.")
        query = urlencode(
            {
                "client_id": settings.gmail_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(self.scopes),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
                "state": state,
            }
        )
        return f"{GOOGLE_AUTH_URL}?{query}"

    async def exchange_code(self, code: str, *, redirect_uri: str) -> dict[str, Any]:
        settings = get_settings()
        if not settings.gmail_client_id or not settings.gmail_client_secret:
            raise GmailOAuthError("Gmail connection is not configured yet.")
        payload = {
            "code": code,
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(GOOGLE_TOKEN_URL, data=payload)
                body = response.json() if response.content else {}
        except httpx.HTTPError as exc:
            log.info("Gmail token exchange failed")
            raise GmailOAuthError("Gmail authorization failed.") from exc
        if response.status_code >= 400 or not isinstance(body, dict):
            log.info("Gmail token exchange rejected")
            raise GmailOAuthError("Gmail authorization failed.")
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GmailOAuthError("Gmail authorization failed.")
        email = await self.fetch_email(access_token)
        stored = {
            "access_token": access_token,
            "refresh_token": body.get("refresh_token") or "",
            "token_type": body.get("token_type") or "Bearer",
            "expires_in": body.get("expires_in"),
            "scope": body.get("scope") or " ".join(self.scopes),
            "email": email or "",
        }
        return stored

    async def fetch_email(self, access_token: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                body = response.json() if response.content else {}
        except httpx.HTTPError:
            log.info("Gmail userinfo lookup failed")
            return ""
        if not isinstance(body, dict):
            return ""
        email = body.get("email")
        return email if isinstance(email, str) else ""

    async def revoke(self, token: str) -> None:
        if not token:
            return
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                await client.post(GOOGLE_REVOKE_URL, data={"token": token})
        except httpx.HTTPError:
            log.info("Gmail token revoke failed; local credentials will still be cleared")

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
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"

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


class GmailApiError(Exception):
    """Read-only Gmail API failure. Messages must never include tokens."""

    def __init__(self, detail: str = "Gmail request failed.") -> None:
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

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token. Response secrets are not logged."""
        settings = get_settings()
        if not settings.gmail_client_id or not settings.gmail_client_secret:
            raise GmailOAuthError("Gmail connection is not configured yet.")
        if not refresh_token:
            raise GmailOAuthError("Gmail authorization is incomplete.")
        payload = {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(GOOGLE_TOKEN_URL, data=payload)
                body = response.json() if response.content else {}
        except httpx.HTTPError as exc:
            log.info("Gmail token refresh failed")
            raise GmailApiError("Gmail authorization failed.") from exc
        if response.status_code >= 400 or not isinstance(body, dict):
            log.info("Gmail token refresh rejected")
            raise GmailApiError("Gmail authorization failed.")
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GmailApiError("Gmail authorization failed.")
        return {
            "access_token": access_token,
            "token_type": body.get("token_type") or "Bearer",
            "expires_in": body.get("expires_in"),
            "scope": body.get("scope") or " ".join(self.scopes),
        }

    async def analyze_recent(
        self,
        credentials: dict[str, Any],
        *,
        query: str,
        max_results: int = 8,
    ) -> tuple[str, dict[str, Any]]:
        """Summarize recent mail. Returns (summary, possibly-refreshed credentials)."""
        creds = dict(credentials)
        access = str(creds.get("access_token") or "")
        headers_list: list[dict[str, str]] | None = None
        if access:
            try:
                headers_list = await self._list_message_headers(
                    access, query=query, max_results=max_results
                )
            except GmailUnauthorized:
                headers_list = None
        if headers_list is None:
            refreshed = await self.refresh_access_token(str(creds.get("refresh_token") or ""))
            creds["access_token"] = refreshed["access_token"]
            creds["token_type"] = refreshed.get("token_type") or creds.get("token_type") or "Bearer"
            if refreshed.get("expires_in") is not None:
                creds["expires_in"] = refreshed["expires_in"]
            headers_list = await self._list_message_headers(
                str(creds["access_token"]),
                query=query,
                max_results=max_results,
            )
        return format_mail_summary(headers_list), creds

    async def _list_message_headers(
        self,
        access_token: str,
        *,
        query: str,
        max_results: int,
    ) -> list[dict[str, str]]:
        listed = await self._gmail_get(
            access_token,
            f"{GMAIL_API}/messages",
            params={"q": query, "maxResults": max(1, min(int(max_results), 20))},
        )
        raw_ids = listed.get("messages") if isinstance(listed.get("messages"), list) else []
        ids: list[str] = []
        for item in raw_ids:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                ids.append(item["id"])
        results: list[dict[str, str]] = []
        for message_id in ids:
            detail = await self._gmail_get(
                access_token,
                f"{GMAIL_API}/messages/{message_id}",
                params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
            )
            results.append(_headers_from_message(detail))
        return results

    async def _gmail_get(
        self,
        access_token: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            log.info("Gmail API request failed")
            raise GmailApiError() from exc
        if response.status_code == 401:
            raise GmailUnauthorized()
        if response.status_code >= 400:
            log.info("Gmail API rejected a read request")
            raise GmailApiError()
        body = response.json() if response.content else {}
        if not isinstance(body, dict):
            raise GmailApiError()
        return body


class GmailUnauthorized(GmailApiError):
    def __init__(self) -> None:
        super().__init__("Gmail authorization expired.")


def _header_value(payload: dict[str, Any], name: str) -> str:
    headers = payload.get("headers")
    if not isinstance(headers, list):
        return ""
    wanted = name.lower()
    for item in headers:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").lower() != wanted:
            continue
        value = item.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return ""


def _headers_from_message(body: dict[str, Any]) -> dict[str, str]:
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    subject = _header_value(payload, "Subject")
    if not subject:
        snippet = body.get("snippet")
        if isinstance(snippet, str) and snippet.strip():
            subject = snippet.strip()[:200]
    if not subject:
        subject = "(no subject)"
    sender = _header_value(payload, "From")
    return {"subject": subject, "from": sender}


def format_mail_summary(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "No recent messages matched this Gmail check."
    lines = [f"{len(messages)} recent message(s):"]
    for item in messages[:8]:
        subject = (item.get("subject") or "(no subject)").replace("\n", " ").strip()
        lines.append(f"- {subject}")
    return "\n".join(lines)

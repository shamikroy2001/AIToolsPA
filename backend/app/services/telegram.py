"""Telegram bot link. The bot token stays in server env; only chat metadata is stored."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.settings import get_settings

log = logging.getLogger("app.telegram")

TELEGRAM_API = "https://api.telegram.org"
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class TelegramLinkError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def telegram_configured() -> bool:
    return bool(get_settings().telegram_bot_token)


def looks_like_bot_token(value: str) -> bool:
    """Reject pasted bot tokens so they never land in the integrations row."""
    text = value.strip()
    return ":" in text and len(text) >= 20


class TelegramService:
    async def verify_chat(self, chat_id: str) -> dict[str, Any]:
        settings = get_settings()
        token = settings.telegram_bot_token
        if not token:
            raise TelegramLinkError("Telegram connection is not configured yet.")
        cleaned = (chat_id or "").strip()
        if not cleaned:
            raise TelegramLinkError("Telegram chat_id is required.")
        if looks_like_bot_token(cleaned):
            raise TelegramLinkError("Telegram chat_id is invalid.")
        url = f"{TELEGRAM_API}/bot{token}/getChat"
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(url, params={"chat_id": cleaned})
                body = response.json() if response.content else {}
        except httpx.HTTPError as exc:
            log.info("Telegram getChat failed")
            raise TelegramLinkError("Telegram chat could not be verified.") from exc
        if not isinstance(body, dict) or not body.get("ok"):
            raise TelegramLinkError("Telegram chat could not be verified.")
        result = body.get("result") if isinstance(body.get("result"), dict) else {}
        username = result.get("username") or result.get("title") or ""
        stored_id = result.get("id", cleaned)
        return {
            "chat_id": str(stored_id),
            "username": username if isinstance(username, str) else "",
        }

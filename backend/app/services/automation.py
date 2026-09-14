from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.crypto import EncryptionUnavailable, decrypt_json, encrypt_json
from app.models.automation import Integration, MonitoredWebsite, Notification, ScheduledTask
from app.schemas.automation import ALLOWED_PROVIDERS, IntegrationPublic
from app.services.gmail import (
    GmailOAuthError,
    GmailService,
    decode_oauth_state,
    encode_oauth_state,
    gmail_configured,
)
from app.services.telegram import TelegramLinkError, TelegramService, telegram_configured


INTEGRATION_CATALOG = (
    {
        "provider": "gmail",
        "name": "Gmail",
        "description": (
            "Connect Gmail so your assistant can read and summarize mail. "
            "Credentials stay on the server."
        ),
    },
    {
        "provider": "telegram",
        "name": "Telegram",
        "description": (
            "Get notified in Telegram when something changes. "
            "Credentials stay on the server."
        ),
    },
)


class IntegrationUnavailable(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class IntegrationBadRequest(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def public_account_label(credentials: dict[str, Any] | None) -> str | None:
    if not credentials:
        return None
    email = credentials.get("email")
    if isinstance(email, str) and email and "@" in email:
        return email
    username = credentials.get("username")
    if isinstance(username, str) and username.strip():
        label = username.strip()
        return label if label.startswith("@") else f"@{label}"
    return None


def _catalog_spec(provider: str) -> dict[str, str]:
    return next(item for item in INTEGRATION_CATALOG if item["provider"] == provider)


def _public_item(
    provider: str,
    *,
    status: str,
    account_label: str | None = None,
    authorize_url: str | None = None,
) -> IntegrationPublic:
    spec = _catalog_spec(provider)
    return IntegrationPublic(
        provider=spec["provider"],
        name=spec["name"],
        description=spec["description"],
        status=status,
        account_label=account_label,
        authorize_url=authorize_url,
    )


def next_run_for(cadence: str, now: datetime | None = None) -> datetime:
    stamp = now or datetime.now(timezone.utc)
    if cadence == "hourly":
        return stamp + timedelta(hours=1)
    if cadence == "weekly":
        return stamp + timedelta(weeks=1)
    return stamp + timedelta(days=1)


def _payload_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _payload_loads(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


class IntegrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gmail = GmailService()
        self._telegram = TelegramService()

    async def _get(
        self, user_id: UUID, provider: str, *, load_secrets: bool = False
    ) -> Integration | None:
        query = select(Integration).where(
            Integration.user_id == user_id,
            Integration.provider == provider,
        )
        if load_secrets:
            query = query.options(undefer(Integration.encrypted_credentials))
        return await self._session.scalar(query)

    def _label_from_row(self, row: Integration | None) -> str | None:
        if row is None or row.status != "connected" or not row.encrypted_credentials:
            return None
        try:
            return public_account_label(decrypt_json(row.encrypted_credentials))
        except Exception:
            return None

    async def catalog(self, user_id: UUID) -> list[IntegrationPublic]:
        result = await self._session.scalars(
            select(Integration)
            .options(undefer(Integration.encrypted_credentials))
            .where(Integration.user_id == user_id)
        )
        by_provider = {row.provider: row for row in result.all()}
        items: list[IntegrationPublic] = []
        for spec in INTEGRATION_CATALOG:
            row = by_provider.get(spec["provider"])
            items.append(
                _public_item(
                    spec["provider"],
                    status=row.status if row is not None else "disconnected",
                    account_label=self._label_from_row(row),
                )
            )
        return items

    async def start_gmail(self, user_id: UUID, *, redirect_uri: str) -> IntegrationPublic:
        if not gmail_configured():
            raise IntegrationUnavailable("Gmail connection is not configured yet.")
        try:
            state = encode_oauth_state(user_id)
            url = self._gmail.authorization_url(redirect_uri=redirect_uri, state=state)
        except EncryptionUnavailable as exc:
            raise IntegrationUnavailable(str(exc)) from exc
        except GmailOAuthError as exc:
            raise IntegrationUnavailable(exc.detail) from exc
        return _public_item("gmail", status="disconnected", authorize_url=url)

    async def complete_gmail(
        self,
        user_id: UUID,
        *,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> IntegrationPublic:
        if not gmail_configured():
            raise IntegrationUnavailable("Gmail connection is not configured yet.")
        if not code or not state:
            raise IntegrationBadRequest("Gmail authorization code is required.")
        try:
            decode_oauth_state(state, expected_user_id=user_id)
            credentials = await self._gmail.exchange_code(code, redirect_uri=redirect_uri)
            row = await self._upsert(user_id, "gmail", credentials=credentials)
        except EncryptionUnavailable as exc:
            raise IntegrationUnavailable(str(exc)) from exc
        except GmailOAuthError as exc:
            raise IntegrationBadRequest(exc.detail) from exc
        return _public_item(
            "gmail",
            status=row.status,
            account_label=public_account_label(credentials),
        )

    async def connect_telegram(self, user_id: UUID, *, chat_id: str | None) -> IntegrationPublic:
        if not telegram_configured():
            raise IntegrationUnavailable("Telegram connection is not configured yet.")
        if not chat_id:
            raise IntegrationBadRequest("Telegram chat_id is required.")
        try:
            credentials = await self._telegram.verify_chat(chat_id)
            row = await self._upsert(user_id, "telegram", credentials=credentials)
        except EncryptionUnavailable as exc:
            raise IntegrationUnavailable(str(exc)) from exc
        except TelegramLinkError as exc:
            if "not configured" in exc.detail.lower():
                raise IntegrationUnavailable(exc.detail) from exc
            raise IntegrationBadRequest(exc.detail) from exc
        return _public_item(
            "telegram",
            status=row.status,
            account_label=public_account_label(credentials),
        )

    async def connect(
        self,
        user_id: UUID,
        provider: str,
        *,
        redirect_uri: str,
        code: str | None = None,
        state: str | None = None,
        chat_id: str | None = None,
    ) -> IntegrationPublic:
        if provider not in ALLOWED_PROVIDERS:
            raise KeyError(provider)
        if provider == "gmail":
            if code or state:
                return await self.complete_gmail(
                    user_id, code=code or "", state=state or "", redirect_uri=redirect_uri
                )
            return await self.start_gmail(user_id, redirect_uri=redirect_uri)
        return await self.connect_telegram(user_id, chat_id=chat_id)

    async def disconnect(self, user_id: UUID, provider: str) -> IntegrationPublic:
        if provider not in ALLOWED_PROVIDERS:
            raise KeyError(provider)
        row = await self._get(user_id, provider, load_secrets=True)
        if row is not None:
            if provider == "gmail" and row.encrypted_credentials:
                token = ""
                try:
                    creds = decrypt_json(row.encrypted_credentials)
                    token = str(creds.get("refresh_token") or creds.get("access_token") or "")
                except Exception:
                    token = ""
                await self._gmail.revoke(token)
            row.status = "disconnected"
            row.encrypted_credentials = ""
            await self._session.flush()
        return _public_item(provider, status="disconnected")

    async def _upsert(
        self, user_id: UUID, provider: str, *, credentials: dict[str, Any]
    ) -> Integration:
        blob = encrypt_json(credentials)
        row = await self._get(user_id, provider, load_secrets=True)
        if row is None:
            row = Integration(
                user_id=user_id,
                provider=provider,
                status="connected",
                encrypted_credentials=blob,
            )
            self._session.add(row)
        else:
            row.status = "connected"
            row.encrypted_credentials = blob
        await self._session.flush()
        return row


class WebsiteMonitorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, user_id: UUID) -> list[MonitoredWebsite]:
        result = await self._session.scalars(
            select(MonitoredWebsite)
            .where(MonitoredWebsite.user_id == user_id)
            .order_by(MonitoredWebsite.created_at.desc())
        )
        return list(result.all())

    async def get(self, user_id: UUID, monitor_id: UUID) -> MonitoredWebsite | None:
        row = await self._session.get(MonitoredWebsite, monitor_id)
        if row is None or row.user_id != user_id:
            return None
        return row

    async def create(self, user_id: UUID, *, url: str, enabled: bool = True) -> MonitoredWebsite:
        row = MonitoredWebsite(user_id=user_id, url=url, enabled=enabled)
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        user_id: UUID,
        monitor_id: UUID,
        *,
        url: str | None = None,
        enabled: bool | None = None,
    ) -> MonitoredWebsite | None:
        row = await self.get(user_id, monitor_id)
        if row is None:
            return None
        if url is not None and url != row.url:
            row.url = url
            row.last_hash = ""
            row.last_checked_at = None
            row.last_changed_at = None
        if enabled is not None:
            row.enabled = enabled
        await self._session.flush()
        return row

    async def delete(self, user_id: UUID, monitor_id: UUID) -> bool:
        row = await self.get(user_id, monitor_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True


class SchedulerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, user_id: UUID) -> list[ScheduledTask]:
        result = await self._session.scalars(
            select(ScheduledTask)
            .where(ScheduledTask.user_id == user_id)
            .order_by(ScheduledTask.created_at.desc())
        )
        return list(result.all())

    async def get(self, user_id: UUID, schedule_id: UUID) -> ScheduledTask | None:
        row = await self._session.get(ScheduledTask, schedule_id)
        if row is None or row.user_id != user_id:
            return None
        return row

    async def create(
        self,
        user_id: UUID,
        *,
        task_type: str,
        cadence: str,
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
        next_run_at: datetime | None = None,
    ) -> ScheduledTask:
        row = ScheduledTask(
            user_id=user_id,
            task_type=task_type,
            cadence=cadence,
            payload=_payload_dumps(payload or {}),
            enabled=enabled,
            next_run_at=next_run_at or next_run_for(cadence),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        user_id: UUID,
        schedule_id: UUID,
        *,
        task_type: str | None = None,
        cadence: str | None = None,
        payload: dict[str, Any] | None = None,
        enabled: bool | None = None,
        next_run_at: datetime | None = None,
    ) -> ScheduledTask | None:
        row = await self.get(user_id, schedule_id)
        if row is None:
            return None
        if task_type is not None:
            row.task_type = task_type
        if cadence is not None:
            row.cadence = cadence
            if next_run_at is None:
                row.next_run_at = next_run_for(cadence)
        if payload is not None:
            row.payload = _payload_dumps(payload)
        if enabled is not None:
            row.enabled = enabled
        if next_run_at is not None:
            row.next_run_at = next_run_at
        await self._session.flush()
        return row

    async def delete(self, user_id: UUID, schedule_id: UUID) -> bool:
        row = await self.get(user_id, schedule_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, user_id: UUID, limit: int = 50) -> list[Notification]:
        result = await self._session.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def create(
        self,
        user_id: UUID,
        *,
        title: str,
        body: str = "",
        channel: str = "in_app",
    ) -> Notification:
        row = Notification(user_id=user_id, title=title, body=body, channel=channel)
        self._session.add(row)
        await self._session.flush()
        return row


def schedule_public_payload(row: ScheduledTask) -> dict[str, Any]:
    return _payload_loads(row.payload)

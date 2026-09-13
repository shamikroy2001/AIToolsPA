from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.automation import Integration, MonitoredWebsite, Notification, ScheduledTask
from app.schemas.automation import ALLOWED_PROVIDERS, IntegrationPublic


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

    async def catalog(self, user_id: UUID) -> list[IntegrationPublic]:
        result = await self._session.scalars(
            select(Integration).where(Integration.user_id == user_id)
        )
        by_provider = {row.provider: row for row in result.all()}
        items: list[IntegrationPublic] = []
        for spec in INTEGRATION_CATALOG:
            row = by_provider.get(spec["provider"])
            items.append(
                IntegrationPublic(
                    provider=spec["provider"],
                    name=spec["name"],
                    description=spec["description"],
                    status=row.status if row is not None else "disconnected",
                )
            )
        return items

    async def connect(self, user_id: UUID, provider: str) -> None:
        del user_id
        if provider not in ALLOWED_PROVIDERS:
            raise KeyError(provider)
        settings = get_settings()
        if provider == "gmail":
            if not settings.gmail_client_id or not settings.gmail_client_secret:
                raise IntegrationUnavailable("Gmail connection is not configured yet.")
            raise IntegrationUnavailable("Gmail connection is not available yet.")
        if not settings.telegram_bot_token:
            raise IntegrationUnavailable("Telegram connection is not configured yet.")
        raise IntegrationUnavailable("Telegram connection is not available yet.")

    async def disconnect(self, user_id: UUID, provider: str) -> IntegrationPublic:
        if provider not in ALLOWED_PROVIDERS:
            raise KeyError(provider)
        row = await self._session.scalar(
            select(Integration).where(
                Integration.user_id == user_id,
                Integration.provider == provider,
            )
        )
        if row is not None:
            row.status = "disconnected"
            row.encrypted_credentials = ""
            await self._session.flush()
        spec = next(item for item in INTEGRATION_CATALOG if item["provider"] == provider)
        return IntegrationPublic(
            provider=spec["provider"],
            name=spec["name"],
            description=spec["description"],
            status="disconnected",
        )


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

"""Due Gmail analyze + Telegram notify jobs for the Arq schedule poller.

Decrypts integration credentials only in this worker/service layer. Tokens are
never logged or written into notifications.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import EncryptionUnavailable
from app.models.assistant import TaskCost
from app.models.automation import ScheduledTask
from app.services.automation import (
    IntegrationService,
    NotificationService,
    next_run_for,
    schedule_public_payload,
)
from app.services.credits import CreditService, InsufficientCredits
from app.services.gmail import GmailApiError, GmailOAuthError, GmailService
from app.services.telegram import TelegramLinkError, TelegramSendError, TelegramService

log = logging.getLogger("app.schedules")

GMAIL_TASK_TYPE = "gmail_analyze"
TELEGRAM_TASK_TYPE = "telegram_notify"
ASSISTANT_TASK_TYPE = "assistant_ask"
DEFAULT_GMAIL_COST = 8
DEFAULT_TELEGRAM_COST = 1
DEFAULT_GMAIL_MAX_RESULTS = 8
DEFAULT_TELEGRAM_MESSAGE = "Scheduled reminder from your assistant."

_TOKENISH = re.compile(
    r"(ya29\.[A-Za-z0-9._\-]+|1//[A-Za-z0-9._\-]+|\d{6,}:[A-Za-z0-9_-]{20,})",
    re.IGNORECASE,
)

GmailAnalyzeFn = Callable[
    [dict[str, Any], dict[str, Any]],
    Awaitable[tuple[str, dict[str, Any]] | None],
]
TelegramSendFn = Callable[[dict[str, Any], str], Awaitable[bool]]


@dataclass(frozen=True)
class ScheduleRunResult:
    advanced: bool
    charged: bool = False
    notified: bool = False
    skipped_reason: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_notice(text: str) -> str:
    return _TOKENISH.sub("[redacted]", text or "")


def gmail_query_for(task: ScheduledTask, payload: dict[str, Any]) -> str:
    query = payload.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()[:256]
    if task.cadence == "hourly":
        return "newer_than:1h"
    if task.cadence == "weekly":
        return "newer_than:7d"
    return "newer_than:1d"


def gmail_max_results(payload: dict[str, Any]) -> int:
    raw = payload.get("max_results", payload.get("limit", DEFAULT_GMAIL_MAX_RESULTS))
    try:
        return max(1, min(int(raw), 20))
    except (TypeError, ValueError):
        return DEFAULT_GMAIL_MAX_RESULTS


def telegram_message_for(payload: dict[str, Any]) -> str:
    for key in ("message", "body", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:4096]
    return DEFAULT_TELEGRAM_MESSAGE


async def estimate_task_cost(
    session: AsyncSession, task_type: str, default: int
) -> int:
    cost = await session.scalar(
        select(TaskCost).where(
            TaskCost.task_type == task_type,
            TaskCost.enabled.is_(True),
        )
    )
    if cost is None:
        return default
    return max(cost.minimum_cost, min(cost.base_credit_cost, cost.maximum_cost))


async def _load_credentials(
    session: AsyncSession, user_id, provider: str
) -> dict[str, Any] | None | str:
    """Return credentials, None if disconnected, or ``'provider_error'`` on decrypt failure."""
    try:
        return await IntegrationService(session).load_connected_credentials(
            user_id, provider
        )
    except EncryptionUnavailable:
        log.info("Skipping %s schedule: credential encryption is not configured", provider)
        return "provider_error"
    except Exception:
        log.info("Skipping %s schedule: stored credentials could not be read", provider)
        return "provider_error"


async def _charge(
    session: AsyncSession,
    user_id,
    amount: int,
    *,
    description: str,
    now: datetime,
) -> bool:
    try:
        await CreditService(session).consume(
            user_id,
            amount,
            description=description,
            now=now,
        )
        return True
    except InsufficientCredits:
        log.info("Skipping %s for user %s: insufficient credits at consume", description, user_id)
        return False


async def run_gmail_analyze(
    session: AsyncSession,
    task: ScheduledTask,
    *,
    now: datetime | None = None,
    analyze: GmailAnalyzeFn | None = None,
) -> ScheduleRunResult:
    stamp = now or _utcnow()
    payload = schedule_public_payload(task)
    cost = await estimate_task_cost(session, GMAIL_TASK_TYPE, DEFAULT_GMAIL_COST)
    credits = CreditService(session)
    if await credits.available(task.user_id, now=stamp) < cost:
        log.info("Skipping gmail schedule %s: insufficient credits", task.id)
        return ScheduleRunResult(False, skipped_reason="insufficient_credits")

    loaded = await _load_credentials(session, task.user_id, "gmail")
    if loaded == "provider_error":
        return ScheduleRunResult(False, skipped_reason="provider_error")
    if not loaded:
        log.info("Skipping gmail schedule %s: Gmail is not connected", task.id)
        return ScheduleRunResult(False, skipped_reason="not_connected")
    credentials = loaded

    summary: str | None = None
    updated = credentials
    try:
        if analyze is not None:
            result = await analyze(credentials, payload)
            if result is None:
                return ScheduleRunResult(False, skipped_reason="provider_error")
            summary, updated = result
        else:
            summary, updated = await GmailService().analyze_recent(
                credentials,
                query=gmail_query_for(task, payload),
                max_results=gmail_max_results(payload),
            )
    except (GmailApiError, GmailOAuthError, EncryptionUnavailable):
        log.info("Gmail analyze failed for schedule %s", task.id)
        return ScheduleRunResult(False, skipped_reason="provider_error")
    except Exception:
        log.info("Gmail analyze failed for schedule %s", task.id)
        return ScheduleRunResult(False, skipped_reason="provider_error")

    if not summary:
        return ScheduleRunResult(False, skipped_reason="provider_error")

    if updated != credentials:
        try:
            await IntegrationService(session).store_credentials(
                task.user_id, "gmail", updated
            )
        except Exception:
            log.info("Could not persist refreshed Gmail credentials")
            return ScheduleRunResult(False, skipped_reason="provider_error")

    if not await _charge(session, task.user_id, cost, description=GMAIL_TASK_TYPE, now=stamp):
        return ScheduleRunResult(False, skipped_reason="insufficient_credits")

    await NotificationService(session).create(
        task.user_id,
        title="Gmail summary",
        body=sanitize_notice(summary),
        channel="in_app",
    )
    task.next_run_at = next_run_for(task.cadence, stamp)
    await session.flush()
    return ScheduleRunResult(advanced=True, charged=True, notified=True)


async def run_telegram_notify(
    session: AsyncSession,
    task: ScheduledTask,
    *,
    now: datetime | None = None,
    send: TelegramSendFn | None = None,
) -> ScheduleRunResult:
    stamp = now or _utcnow()
    payload = schedule_public_payload(task)
    message = telegram_message_for(payload)
    cost = await estimate_task_cost(session, TELEGRAM_TASK_TYPE, DEFAULT_TELEGRAM_COST)
    credits = CreditService(session)
    if await credits.available(task.user_id, now=stamp) < cost:
        log.info("Skipping telegram schedule %s: insufficient credits", task.id)
        return ScheduleRunResult(False, skipped_reason="insufficient_credits")

    loaded = await _load_credentials(session, task.user_id, "telegram")
    if loaded == "provider_error":
        return ScheduleRunResult(False, skipped_reason="provider_error")
    if not loaded:
        log.info("Skipping telegram schedule %s: Telegram is not connected", task.id)
        return ScheduleRunResult(False, skipped_reason="not_connected")
    credentials = loaded
    chat_id = str(credentials.get("chat_id") or "").strip()
    if not chat_id:
        log.info("Skipping telegram schedule %s: chat metadata missing", task.id)
        return ScheduleRunResult(False, skipped_reason="not_connected")

    try:
        if send is not None:
            delivered = await send(credentials, message)
            if not delivered:
                return ScheduleRunResult(False, skipped_reason="provider_error")
        else:
            await TelegramService().send_message(chat_id, message)
    except (TelegramLinkError, TelegramSendError, EncryptionUnavailable):
        log.info("Telegram notify failed for schedule %s", task.id)
        return ScheduleRunResult(False, skipped_reason="provider_error")
    except Exception:
        log.info("Telegram notify failed for schedule %s", task.id)
        return ScheduleRunResult(False, skipped_reason="provider_error")

    if not await _charge(
        session, task.user_id, cost, description=TELEGRAM_TASK_TYPE, now=stamp
    ):
        return ScheduleRunResult(False, skipped_reason="insufficient_credits")

    await NotificationService(session).create(
        task.user_id,
        title="Telegram reminder sent",
        body=sanitize_notice(message),
        channel="in_app",
    )
    task.next_run_at = next_run_for(task.cadence, stamp)
    await session.flush()
    return ScheduleRunResult(advanced=True, charged=True, notified=True)

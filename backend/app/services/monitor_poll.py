"""Website monitor hash-check + due schedule handling for the Arq worker.

Gmail/Telegram credentials are decrypted only in the schedule job layer.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import TaskCost
from app.models.automation import MonitoredWebsite, ScheduledTask
from app.services.automation import NotificationService, next_run_for
from app.services.credits import CreditService, InsufficientCredits
from app.services.schedule_jobs import (
    ASSISTANT_TASK_TYPE,
    GMAIL_TASK_TYPE,
    TELEGRAM_TASK_TYPE,
    GmailAnalyzeFn,
    ScheduleRunResult,
    TelegramSendFn,
    run_gmail_analyze,
    run_telegram_notify,
)

log = logging.getLogger("app.monitors")

MONITOR_TASK_TYPE = "website_monitor"
DEFAULT_MONITOR_COST = 3
MONITOR_STALE_AFTER = timedelta(minutes=15)
MONITOR_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MONITOR_MAX_BODY_BYTES = 1_000_000
MONITOR_USER_AGENT = "AIToolsPA-Monitor/1.0"

FetchFn = Callable[[str], Awaitable[bytes | None]]


@dataclass(frozen=True)
class MonitorCheckResult:
    checked: bool
    changed: bool
    notified: bool
    charged: bool
    skipped_reason: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(stamp: datetime | None) -> datetime | None:
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


async def fetch_url(url: str, *, client: httpx.AsyncClient | None = None) -> bytes | None:
    """GET the URL. Returns body bytes or None on any HTTP/network failure."""
    target = (url or "").strip()
    if not (target.startswith("http://") or target.startswith("https://")):
        return None
    headers = {"User-Agent": MONITOR_USER_AGENT, "Accept": "*/*"}
    own_client = client is None
    http = client or httpx.AsyncClient(
        timeout=MONITOR_TIMEOUT,
        follow_redirects=True,
        headers=headers,
    )
    try:
        response = await http.get(target)
        response.raise_for_status()
        return response.content[:MONITOR_MAX_BODY_BYTES]
    except httpx.HTTPError:
        return None
    finally:
        if own_client:
            await http.aclose()


async def estimate_website_monitor_cost(session: AsyncSession) -> int:
    cost = await session.scalar(
        select(TaskCost).where(
            TaskCost.task_type == MONITOR_TASK_TYPE,
            TaskCost.enabled.is_(True),
        )
    )
    if cost is None:
        return DEFAULT_MONITOR_COST
    return max(cost.minimum_cost, min(cost.base_credit_cost, cost.maximum_cost))


async def list_due_monitors(
    session: AsyncSession, *, now: datetime | None = None
) -> list[MonitoredWebsite]:
    stamp = now or _utcnow()
    cutoff = stamp - MONITOR_STALE_AFTER
    result = await session.scalars(
        select(MonitoredWebsite).where(
            MonitoredWebsite.enabled.is_(True),
            or_(
                MonitoredWebsite.last_checked_at.is_(None),
                MonitoredWebsite.last_checked_at <= cutoff,
            ),
        )
    )
    return list(result.all())


async def list_due_schedules(
    session: AsyncSession, *, now: datetime | None = None
) -> list[ScheduledTask]:
    stamp = now or _utcnow()
    result = await session.scalars(
        select(ScheduledTask).where(
            ScheduledTask.enabled.is_(True),
            or_(
                ScheduledTask.next_run_at.is_(None),
                ScheduledTask.next_run_at <= stamp,
            ),
        )
    )
    return list(result.all())


async def check_monitor(
    session: AsyncSession,
    monitor: MonitoredWebsite,
    *,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
) -> MonitorCheckResult:
    """Hash-check one enabled monitor.

    Credit behavior:
    - Cost comes from ``task_costs.website_monitor`` (default 3).
    - Credits are charged only after a successful HTTP GET.
    - Insufficient credits fail soft: no fetch, no notification, ``last_checked_at``
      stays unchanged so the row remains due. Other monitors still run.
    - HTTP failure: no charge, no notification, ``last_checked_at`` unchanged.
    - Unchanged content still charges (the check itself is the billed work).
    - First successful check (empty ``last_hash``) stores a baseline and does
      not notify.
    """
    stamp = now or _utcnow()
    getter = fetch or fetch_url
    credits = CreditService(session)
    cost = await estimate_website_monitor_cost(session)

    available = await credits.available(monitor.user_id, now=stamp)
    if available < cost:
        log.info(
            "Skipping monitor %s for user %s: insufficient credits",
            monitor.id,
            monitor.user_id,
        )
        return MonitorCheckResult(False, False, False, False, "insufficient_credits")

    body = await getter(monitor.url)
    if body is None:
        log.info("Monitor %s fetch failed for %s", monitor.id, monitor.url)
        return MonitorCheckResult(False, False, False, False, "fetch_failed")

    digest = content_hash(body)
    previous = monitor.last_hash or ""
    is_baseline = previous == ""
    changed = (not is_baseline) and digest != previous

    try:
        await credits.consume(
            monitor.user_id,
            cost,
            description=MONITOR_TASK_TYPE,
            now=stamp,
        )
    except InsufficientCredits:
        log.info(
            "Skipping monitor %s for user %s: insufficient credits at consume",
            monitor.id,
            monitor.user_id,
        )
        return MonitorCheckResult(False, False, False, False, "insufficient_credits")

    monitor.last_hash = digest
    monitor.last_checked_at = stamp
    notified = False
    if changed:
        monitor.last_changed_at = stamp
        await NotificationService(session).create(
            monitor.user_id,
            title="Website change detected",
            body=f"Content changed at {monitor.url}",
            channel="in_app",
        )
        notified = True
    await session.flush()
    return MonitorCheckResult(
        checked=True,
        changed=changed,
        notified=notified,
        charged=True,
    )


async def process_scheduled_task(
    session: AsyncSession,
    task: ScheduledTask,
    *,
    now: datetime | None = None,
    gmail_analyze: GmailAnalyzeFn | None = None,
    telegram_send: TelegramSendFn | None = None,
) -> ScheduleRunResult:
    """Run due Gmail/Telegram jobs; bump website_monitor; skip assistant_ask.

    Fail-soft: missing integration, insufficient credits, or provider errors
    leave ``next_run_at`` unchanged so the next cron retries. Other due
    schedules still run. ``assistant_ask`` stays unimplemented for a later slice.
    """
    stamp = now or _utcnow()
    if not task.enabled:
        return ScheduleRunResult(False, skipped_reason="disabled")
    due_at = _aware(task.next_run_at)
    if due_at is not None and due_at > stamp:
        return ScheduleRunResult(False, skipped_reason="not_due")
    if task.task_type == ASSISTANT_TASK_TYPE:
        log.info("Skipping unimplemented assistant schedule %s", task.id)
        return ScheduleRunResult(False, skipped_reason="unimplemented")
    if task.task_type == MONITOR_TASK_TYPE:
        task.next_run_at = next_run_for(task.cadence, stamp)
        await session.flush()
        return ScheduleRunResult(advanced=True)
    if task.task_type == GMAIL_TASK_TYPE:
        return await run_gmail_analyze(
            session, task, now=stamp, analyze=gmail_analyze
        )
    if task.task_type == TELEGRAM_TASK_TYPE:
        return await run_telegram_notify(
            session, task, now=stamp, send=telegram_send
        )
    return ScheduleRunResult(False, skipped_reason="unknown")


async def poll_due_monitors_in_session(
    session: AsyncSession,
    *,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
    gmail_analyze: GmailAnalyzeFn | None = None,
    telegram_send: TelegramSendFn | None = None,
) -> int:
    """Check due monitors and run due schedules in one session."""
    stamp = now or _utcnow()
    checked = 0
    for monitor in await list_due_monitors(session, now=stamp):
        result = await check_monitor(session, monitor, fetch=fetch, now=stamp)
        if result.checked:
            checked += 1
    for task in await list_due_schedules(session, now=stamp):
        await process_scheduled_task(
            session,
            task,
            now=stamp,
            gmail_analyze=gmail_analyze,
            telegram_send=telegram_send,
        )
    return checked


async def run_poll_cycle(
    *,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
    gmail_analyze: GmailAnalyzeFn | None = None,
    telegram_send: TelegramSendFn | None = None,
) -> int:
    """Admin-list due work, then apply ``app.user_id`` per tenant write."""
    from app.core.db import admin_session_factory, apply_tenant, init_engines_from_settings

    init_engines_from_settings()
    factory = admin_session_factory()
    stamp = now or _utcnow()

    async with factory() as session:
        monitor_ids = [(row.id, row.user_id) for row in await list_due_monitors(session, now=stamp)]
        schedule_ids = [(row.id, row.user_id) for row in await list_due_schedules(session, now=stamp)]

    checked = 0
    for monitor_id, user_id in monitor_ids:
        try:
            async with factory() as session:
                await apply_tenant(session, user_id)
                monitor = await session.get(MonitoredWebsite, monitor_id)
                if monitor is None or monitor.user_id != user_id or not monitor.enabled:
                    continue
                result = await check_monitor(session, monitor, fetch=fetch, now=stamp)
                await session.commit()
                if result.checked:
                    checked += 1
        except Exception:
            log.exception("Monitor check failed for %s", monitor_id)

    for schedule_id, user_id in schedule_ids:
        try:
            async with factory() as session:
                await apply_tenant(session, user_id)
                task = await session.get(ScheduledTask, schedule_id)
                if task is None or task.user_id != user_id:
                    continue
                await process_scheduled_task(
                    session,
                    task,
                    now=stamp,
                    gmail_analyze=gmail_analyze,
                    telegram_send=telegram_send,
                )
                await session.commit()
        except Exception:
            log.exception("Scheduled task failed for %s", schedule_id)

    return checked

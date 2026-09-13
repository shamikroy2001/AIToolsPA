"""Website monitor worker: hash change, no-op on same hash, credit charge."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.models.assistant import TaskCost
from app.models.automation import MonitoredWebsite, Notification, ScheduledTask
from app.models.base import Base
from app.models.credit import SOURCE_MONTHLY, CreditLot, CreditTransaction
from app.models.user import User
from app.services.credits import CreditService
from app.services.monitor_poll import (
    check_monitor,
    content_hash,
    poll_due_monitors_in_session,
    process_scheduled_task,
)


HELLO = b"<html>hello</html>"
WORLD = b"<html>world</html>"
HELLO_HASH = content_hash(HELLO)
NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def _user_with_credits(session: AsyncSession, amount: int = 30) -> User:
    user = User(id=uuid4(), clerk_user_id=f"clerk_{uuid4().hex[:8]}", email="m@example.com")
    session.add(user)
    existing_cost = await session.scalar(
        select(TaskCost).where(TaskCost.task_type == "website_monitor")
    )
    if existing_cost is None:
        session.add(
            TaskCost(
                task_type="website_monitor",
                base_credit_cost=3,
                minimum_cost=1,
                maximum_cost=15,
                enabled=True,
            )
        )
    if amount:
        session.add(
            CreditLot(
                user_id=user.id,
                source=SOURCE_MONTHLY,
                original_amount=amount,
                remaining_amount=amount,
                billing_period="2026-09",
                expires_at=None,
            )
        )
    await session.flush()
    return user


async def _monitor(
    session: AsyncSession,
    user: User,
    *,
    last_hash: str = "",
    last_checked_at: datetime | None = None,
    enabled: bool = True,
    url: str = "https://example.com/status",
) -> MonitoredWebsite:
    row = MonitoredWebsite(
        user_id=user.id,
        url=url,
        enabled=enabled,
        last_hash=last_hash,
        last_checked_at=last_checked_at,
    )
    session.add(row)
    await session.flush()
    return row


def _fetch(body: bytes | None):
    async def _inner(url: str) -> bytes | None:
        del url
        return body

    return _inner


def _counting_fetch(body: bytes | None, calls: list[str]):
    async def _inner(url: str) -> bytes | None:
        calls.append(url)
        return body

    return _inner


@pytest.mark.asyncio
async def test_hash_change_creates_in_app_notification(session: AsyncSession):
    user = await _user_with_credits(session)
    monitor = await _monitor(session, user, last_hash=HELLO_HASH)

    result = await check_monitor(session, monitor, fetch=_fetch(WORLD), now=NOW)

    assert result.checked is True
    assert result.changed is True
    assert result.notified is True
    assert result.charged is True
    assert monitor.last_hash == content_hash(WORLD)
    assert monitor.last_changed_at == NOW
    assert monitor.last_checked_at == NOW

    notices = list(
        (
            await session.scalars(
                select(Notification).where(Notification.user_id == user.id)
            )
        ).all()
    )
    assert len(notices) == 1
    assert notices[0].channel == "in_app"
    assert "example.com" in notices[0].body
    payload = str(notices[0].title) + str(notices[0].body)
    for forbidden in ("token", "secret", "credential", "api_key"):
        assert forbidden not in payload.lower()


@pytest.mark.asyncio
async def test_unchanged_hash_does_not_create_notification(session: AsyncSession):
    user = await _user_with_credits(session)
    monitor = await _monitor(session, user, last_hash=HELLO_HASH)

    result = await check_monitor(session, monitor, fetch=_fetch(HELLO), now=NOW)

    assert result.checked is True
    assert result.changed is False
    assert result.notified is False
    assert monitor.last_hash == HELLO_HASH
    assert monitor.last_changed_at is None
    assert monitor.last_checked_at == NOW
    notices = list(
        (
            await session.scalars(
                select(Notification).where(Notification.user_id == user.id)
            )
        ).all()
    )
    assert notices == []


@pytest.mark.asyncio
async def test_successful_check_charges_website_monitor_credits(session: AsyncSession):
    user = await _user_with_credits(session, amount=30)
    monitor = await _monitor(session, user, last_hash=HELLO_HASH)
    credits = CreditService(session)
    before = await credits.available(user.id, now=NOW)

    result = await check_monitor(session, monitor, fetch=_fetch(HELLO), now=NOW)

    assert result.charged is True
    assert await credits.available(user.id, now=NOW) == before - 3
    txs = list(
        (
            await session.scalars(
                select(CreditTransaction).where(
                    CreditTransaction.user_id == user.id,
                    CreditTransaction.description == "website_monitor",
                )
            )
        ).all()
    )
    assert sum(row.amount for row in txs) == -3


@pytest.mark.asyncio
async def test_insufficient_credits_skips_without_fetch_or_notification(
    session: AsyncSession,
):
    user = await _user_with_credits(session, amount=0)
    monitor = await _monitor(session, user, last_hash=HELLO_HASH)
    calls: list[str] = []

    result = await check_monitor(
        session, monitor, fetch=_counting_fetch(WORLD, calls), now=NOW
    )

    assert result.skipped_reason == "insufficient_credits"
    assert result.checked is False
    assert result.notified is False
    assert result.charged is False
    assert calls == []
    assert monitor.last_hash == HELLO_HASH
    assert monitor.last_checked_at is None
    notices = list(
        (
            await session.scalars(
                select(Notification).where(Notification.user_id == user.id)
            )
        ).all()
    )
    assert notices == []


@pytest.mark.asyncio
async def test_fetch_failure_does_not_charge_or_notify(session: AsyncSession):
    user = await _user_with_credits(session, amount=30)
    monitor = await _monitor(session, user, last_hash=HELLO_HASH)
    credits = CreditService(session)
    before = await credits.available(user.id, now=NOW)

    result = await check_monitor(session, monitor, fetch=_fetch(None), now=NOW)

    assert result.skipped_reason == "fetch_failed"
    assert result.charged is False
    assert result.notified is False
    assert monitor.last_hash == HELLO_HASH
    assert monitor.last_checked_at is None
    assert await credits.available(user.id, now=NOW) == before


@pytest.mark.asyncio
async def test_first_check_stores_baseline_without_notification(session: AsyncSession):
    user = await _user_with_credits(session)
    monitor = await _monitor(session, user, last_hash="")

    result = await check_monitor(session, monitor, fetch=_fetch(HELLO), now=NOW)

    assert result.checked is True
    assert result.changed is False
    assert result.notified is False
    assert monitor.last_hash == HELLO_HASH
    assert monitor.last_changed_at is None
    notices = list(
        (
            await session.scalars(
                select(Notification).where(Notification.user_id == user.id)
            )
        ).all()
    )
    assert notices == []


@pytest.mark.asyncio
async def test_poll_skips_disabled_and_recently_checked(session: AsyncSession):
    user = await _user_with_credits(session)
    await _monitor(session, user, last_hash=HELLO_HASH, enabled=False)
    await _monitor(
        session,
        user,
        last_hash=HELLO_HASH,
        last_checked_at=NOW - timedelta(minutes=5),
        url="https://example.com/fresh",
    )
    due = await _monitor(
        session,
        user,
        last_hash=HELLO_HASH,
        last_checked_at=NOW - timedelta(minutes=20),
        url="https://example.com/due",
    )
    calls: list[str] = []

    checked = await poll_due_monitors_in_session(
        session, fetch=_counting_fetch(WORLD, calls), now=NOW
    )

    assert checked == 1
    assert calls == ["https://example.com/due"]
    reloaded = await session.get(MonitoredWebsite, due.id)
    assert reloaded is not None
    assert reloaded.last_hash == content_hash(WORLD)


@pytest.mark.asyncio
async def test_credential_gated_schedules_are_left_due(session: AsyncSession):
    user = await _user_with_credits(session)
    gated = ScheduledTask(
        user_id=user.id,
        task_type="gmail_analyze",
        cadence="daily",
        payload="{}",
        enabled=True,
        next_run_at=NOW - timedelta(hours=1),
    )
    telegram = ScheduledTask(
        user_id=user.id,
        task_type="telegram_notify",
        cadence="hourly",
        payload="{}",
        enabled=True,
        next_run_at=NOW - timedelta(minutes=5),
    )
    site = ScheduledTask(
        user_id=user.id,
        task_type="website_monitor",
        cadence="daily",
        payload="{}",
        enabled=True,
        next_run_at=NOW - timedelta(hours=1),
    )
    session.add_all([gated, telegram, site])
    await session.flush()

    assert await process_scheduled_task(session, gated, now=NOW) is False
    assert await process_scheduled_task(session, telegram, now=NOW) is False
    assert await process_scheduled_task(session, site, now=NOW) is True
    assert gated.next_run_at == NOW - timedelta(hours=1)
    assert telegram.next_run_at == NOW - timedelta(minutes=5)
    assert site.next_run_at == NOW + timedelta(days=1)

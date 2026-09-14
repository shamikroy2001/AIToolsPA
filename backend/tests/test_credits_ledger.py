"""Credit lots, rollover, expiry, consumption order. No Stripe network."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.plan_catalog import DEFAULT_PLANS
from app.models.base import Base
from app.models.credit import TX_RESERVATION, CreditTransaction
from app.models.plan import Plan
from app.models.user import User
from app.services.credits import CreditService, InsufficientCredits


@pytest.fixture
async def credit_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _user_and_plan(session: AsyncSession, slug: str = "pro") -> tuple[User, Plan]:
    seed = next(p for p in DEFAULT_PLANS if p["slug"] == slug)
    plan = Plan(**seed)
    user = User(id=uuid4(), clerk_user_id="c1", email="a@example.com")
    session.add(plan)
    session.add(user)
    await session.flush()
    return user, plan


@pytest.mark.asyncio
async def test_monthly_allocation(credit_session: AsyncSession):
    user, plan = await _user_and_plan(credit_session)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    credits = CreditService(credit_session)
    assert await credits.allocate_period(user, plan, start, end) is True
    assert await credits.available(user.id, now=start + timedelta(days=1)) == 5000
    assert await credits.allocate_period(user, plan, start, end) is False
    assert await credits.available(user.id, now=start + timedelta(days=1)) == 5000


@pytest.mark.asyncio
async def test_rollover_cap(credit_session: AsyncSession):
    user, plan = await _user_and_plan(credit_session)
    credits = CreditService(credit_session)
    p1s = datetime(2026, 7, 1, tzinfo=timezone.utc)
    p1e = datetime(2026, 8, 1, tzinfo=timezone.utc)
    p2s = datetime(2026, 8, 1, tzinfo=timezone.utc)
    p2e = datetime(2026, 9, 1, tzinfo=timezone.utc)
    await credits.allocate_period(user, plan, p1s, p1e, now=p1s)
    await credits.consume(user.id, 2000, now=p1s + timedelta(days=2), description="use")
    # 3000 unused, cap 5000 -> rollover 3000 + new 5000 = 8000
    await credits.allocate_period(user, plan, p2s, p2e, now=p2s)
    now = p2s + timedelta(days=1)
    assert await credits.available(user.id, now=now) == 8000
    assert await credits.rollover_available(user.id, now=now) == 3000


@pytest.mark.asyncio
async def test_rollover_capped_at_plan_limit(credit_session: AsyncSession):
    user, plan = await _user_and_plan(credit_session, slug="basic")
    credits = CreditService(credit_session)
    p1s = datetime(2026, 7, 1, tzinfo=timezone.utc)
    p1e = datetime(2026, 8, 1, tzinfo=timezone.utc)
    p2s = datetime(2026, 8, 1, tzinfo=timezone.utc)
    p2e = datetime(2026, 9, 1, tzinfo=timezone.utc)
    await credits.allocate_period(user, plan, p1s, p1e, now=p1s)
    # unused 1000, cap 1000
    await credits.allocate_period(user, plan, p2s, p2e, now=p2s)
    now = p2s + timedelta(days=1)
    assert await credits.available(user.id, now=now) == 2000
    assert await credits.rollover_available(user.id, now=now) == 1000


@pytest.mark.asyncio
async def test_rollover_expires(credit_session: AsyncSession):
    user, plan = await _user_and_plan(credit_session)
    credits = CreditService(credit_session)
    p1s = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p1e = datetime(2026, 2, 1, tzinfo=timezone.utc)
    p2s = datetime(2026, 2, 1, tzinfo=timezone.utc)
    p2e = datetime(2026, 3, 1, tzinfo=timezone.utc)
    await credits.allocate_period(user, plan, p1s, p1e, now=p1s)
    await credits.allocate_period(user, plan, p2s, p2e, now=p2s)
    later = p2s + timedelta(days=91)
    expired = await credits.expire_due_lots(user.id, now=later)
    assert expired == 5000
    assert await credits.rollover_available(user.id, now=later) == 0
    assert await credits.available(user.id, now=later) == 5000


@pytest.mark.asyncio
async def test_consume_expiring_rollover_first(credit_session: AsyncSession):
    user, plan = await _user_and_plan(credit_session)
    credits = CreditService(credit_session)
    p1s = datetime(2026, 7, 1, tzinfo=timezone.utc)
    p1e = datetime(2026, 8, 1, tzinfo=timezone.utc)
    p2s = datetime(2026, 8, 1, tzinfo=timezone.utc)
    p2e = datetime(2026, 9, 1, tzinfo=timezone.utc)
    await credits.allocate_period(user, plan, p1s, p1e, now=p1s)
    await credits.allocate_period(user, plan, p2s, p2e, now=p2s)
    now = p2s + timedelta(days=1)
    await credits.consume(user.id, 5000, now=now)
    assert await credits.rollover_available(user.id, now=now) == 0
    assert await credits.available(user.id, now=now) == 5000


@pytest.mark.asyncio
async def test_insufficient_credits(credit_session: AsyncSession):
    user, plan = await _user_and_plan(credit_session, slug="basic")
    credits = CreditService(credit_session)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    await credits.allocate_period(user, plan, start, end, now=start)
    with pytest.raises(InsufficientCredits):
        await credits.consume(user.id, 1001, now=start + timedelta(days=1))


@pytest.mark.asyncio
async def test_reserve_writes_timezone_aware_created_at(credit_session: AsyncSession):
    """Live ask 503'd on CreditTransaction.created_at naive bind during reserve."""
    user, plan = await _user_and_plan(credit_session)
    credits = CreditService(credit_session)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    await credits.allocate_period(user, plan, start, end, now=start)
    task_id = uuid4()
    await credits.reserve(user.id, 5, task_id=task_id)
    row = await credit_session.scalar(
        select(CreditTransaction).where(
            CreditTransaction.task_id == task_id,
            CreditTransaction.transaction_type == TX_RESERVATION,
        )
    )
    assert row is not None
    assert row.amount == -5
    assert CreditTransaction.__table__.c.created_at.type.timezone is True
    assert await credits.available(user.id, now=start + timedelta(days=1)) == 4995

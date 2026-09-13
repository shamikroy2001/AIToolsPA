"""Arq worker. D1-staging: ping + expire credit lots + no-op monitor poll."""

from arq.connections import RedisSettings
from arq import cron

from app.core.db import admin_session_factory, init_engines_from_settings
from app.core.settings import get_settings
from app.services.credits import CreditService


async def ping(ctx: dict) -> str:
    return "ok"


async def expire_credit_lots(ctx: dict) -> int:
    init_engines_from_settings()
    factory = admin_session_factory()
    async with factory() as session:
        expired = await CreditService(session).expire_due_lots()
        await session.commit()
        return expired


async def poll_due_monitors(ctx: dict) -> int:
    """No-op cron so Arq is proven. Real hash-check polling is a later slice."""
    return 0


class WorkerSettings:
    functions = [ping, expire_credit_lots, poll_due_monitors]
    cron_jobs = [
        cron(expire_credit_lots, hour={3}, minute={15}),
        cron(poll_due_monitors, minute={0, 15, 30, 45}),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

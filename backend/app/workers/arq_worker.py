"""Arq worker. D1-staging: ping + expire credit lots. Integration jobs are D2."""

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


class WorkerSettings:
    functions = [ping, expire_credit_lots]
    cron_jobs = [cron(expire_credit_lots, hour={3}, minute={15})]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

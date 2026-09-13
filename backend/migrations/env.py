from logging.config import fileConfig
import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import engine_connect_args
from app.core.dsn import to_async_sqlalchemy, to_sync_psycopg, with_required_ssl
from app.core.settings import get_settings
from app.models.base import Base
from app.models import assistant as _assistant  # noqa: F401
from app.models import credit as _credit  # noqa: F401
from app.models import plan as _plan  # noqa: F401
from app.models import stripe_event as _stripe_event  # noqa: F401
from app.models import subscription as _subscription  # noqa: F401
from app.models import user as _user  # noqa: F401

try:
    from app.models import automation as _automation  # noqa: F401
except ImportError:
    pass

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _admin_url() -> str:
    settings = get_settings()
    return settings.database_admin_url or settings.database_url


def _sync_admin_url() -> str:
    return with_required_ssl(to_sync_psycopg(_admin_url()))


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_admin_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = to_async_sqlalchemy(_admin_url())
    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
        connect_args=engine_connect_args(url),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Use asyncpg (same TLS as the API). psycopg never reaches the Supabase pooler."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.dsn import to_sync_psycopg, with_required_ssl
from app.core.settings import get_settings
from app.models.base import Base
from app.models import assistant as _assistant  # noqa: F401
from app.models import credit as _credit  # noqa: F401
from app.models import plan as _plan  # noqa: F401
from app.models import stripe_event as _stripe_event  # noqa: F401
from app.models import subscription as _subscription  # noqa: F401
from app.models import user as _user  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_admin_url() -> str:
    settings = get_settings()
    url = settings.database_admin_url or settings.database_url
    return with_required_ssl(to_sync_psycopg(url))


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_admin_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _sync_admin_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 15},
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

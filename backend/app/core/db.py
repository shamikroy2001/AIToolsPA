"""SQLAlchemy engines. App role is RLS-bound; admin role upserts users on first login."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.dsn import needs_ssl
from app.core.settings import Settings, get_settings

_app_engine: AsyncEngine | None = None
_admin_engine: AsyncEngine | None = None
_AppSession: async_sessionmaker[AsyncSession] | None = None
_AdminSession: async_sessionmaker[AsyncSession] | None = None


def _make_engine(url: str) -> AsyncEngine:
    kwargs: dict = {"pool_pre_ping": True, "pool_timeout": 15}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    elif needs_ssl(url):
        kwargs["connect_args"] = {"ssl": True, "timeout": 15}
    return create_async_engine(url, **kwargs)


def configure_engines(
    *,
    app_url: str,
    admin_url: str | None = None,
) -> None:
    global _app_engine, _admin_engine, _AppSession, _AdminSession
    _app_engine = _make_engine(app_url)
    _admin_engine = _make_engine(admin_url or app_url)
    _AppSession = async_sessionmaker(_app_engine, expire_on_commit=False)
    _AdminSession = async_sessionmaker(_admin_engine, expire_on_commit=False)


def init_engines_from_settings(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    configure_engines(
        app_url=settings.database_url,
        admin_url=settings.database_admin_url,
    )


def get_app_engine() -> AsyncEngine | None:
    return _app_engine


def app_session_factory() -> async_sessionmaker[AsyncSession]:
    if _AppSession is None:
        init_engines_from_settings()
    assert _AppSession is not None
    return _AppSession


def admin_session_factory() -> async_sessionmaker[AsyncSession]:
    if _AdminSession is None:
        init_engines_from_settings()
    assert _AdminSession is not None
    return _AdminSession


async def apply_tenant(session: AsyncSession, user_id: UUID) -> None:
    bind = session.bind
    if bind is not None and bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT set_config('app.user_id', :id, true)"),
            {"id": str(user_id)},
        )


async def get_admin_session() -> AsyncIterator[AsyncSession]:
    factory = admin_session_factory()
    async with factory() as session:
        yield session


async def get_tenant_session(user_id: UUID) -> AsyncIterator[AsyncSession]:
    factory = app_session_factory()
    async with factory() as session:
        await apply_tenant(session, user_id)
        yield session

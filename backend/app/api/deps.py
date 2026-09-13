import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ClerkTokenVerifier, TokenVerifier
from app.core.db import admin_session_factory, apply_tenant, app_session_factory
from app.core.settings import get_settings
from app.models.user import User
from app.services.users import UserService

log = logging.getLogger("app.db")

_verifier: TokenVerifier | None = None


def set_token_verifier(verifier: TokenVerifier | None) -> None:
    global _verifier
    _verifier = verifier


def get_token_verifier() -> TokenVerifier:
    if _verifier is not None:
        return _verifier
    return ClerkTokenVerifier(get_settings())


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    token = header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return token


async def get_current_user(
    request: Request,
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> User:
    token = _bearer_token(request)
    principal = verifier.verify(token)
    factory = admin_session_factory()
    async with factory() as session:
        return await UserService(session).get_or_create(principal)


async def get_tenant_db(
    user: Annotated[User, Depends(get_current_user)],
) -> AsyncSession:
    factory = app_session_factory()
    async with factory() as session:
        await apply_tenant(session, user.id)
        try:
            yield session
            await session.commit()
        except Exception:
            log.exception("Tenant session failed user_id=%s", user.id)
            await session.rollback()
            raise


async def get_admin_db(
    user: Annotated[User, Depends(get_current_user)],
) -> AsyncSession:
    """Admin/postgres role with ``app.user_id`` set.

    ``FORCE ROW LEVEL SECURITY`` applies to table owners. A profile/task
    INSERT without ``app.user_id`` fails ``WITH CHECK`` unless the role
    has ``BYPASSRLS`` (superuser). ``GET /api/me`` works because that
    upsert uses this engine as a superuser; assistant tables still need
    the GUC when the admin role is not a superuser.
    """
    factory = admin_session_factory()
    async with factory() as session:
        await apply_tenant(session, user.id)
        try:
            yield session
            await session.commit()
        except Exception:
            log.exception("Admin session failed user_id=%s", user.id)
            await session.rollback()
            raise

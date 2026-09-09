from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ClerkTokenVerifier, TokenVerifier
from app.core.db import admin_session_factory, apply_tenant, app_session_factory
from app.core.settings import get_settings
from app.models.user import User
from app.services.users import UserService

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
            await session.rollback()
            raise

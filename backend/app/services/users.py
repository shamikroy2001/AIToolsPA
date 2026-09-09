from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principals import ClerkPrincipal
from app.models.user import User


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_clerk_id(self, clerk_user_id: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.clerk_user_id == clerk_user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, principal: ClerkPrincipal) -> User:
        existing = await self.get_by_clerk_id(principal.clerk_user_id)
        if existing is not None:
            if principal.email and existing.email != principal.email:
                existing.email = principal.email
                await self._session.commit()
                await self._session.refresh(existing)
            return existing
        user = User(
            clerk_user_id=principal.clerk_user_id,
            email=principal.email,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

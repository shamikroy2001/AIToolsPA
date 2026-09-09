from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_catalog import DEFAULT_PLANS
from app.core.settings import Settings
from app.models.plan import Plan


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_defaults(self) -> None:
        for seed in DEFAULT_PLANS:
            existing = await self._session.scalar(select(Plan).where(Plan.slug == seed["slug"]))
            if existing is None:
                self._session.add(Plan(**seed))
        await self._session.flush()

    async def list_enabled(self) -> list[Plan]:
        result = await self._session.scalars(
            select(Plan).where(Plan.enabled.is_(True)).order_by(Plan.sort_order)
        )
        return list(result.all())

    async def get_by_slug(self, slug: str) -> Plan | None:
        return await self._session.scalar(select(Plan).where(Plan.slug == slug))

    async def get_by_price_id(self, price_id: str, settings: Settings) -> Plan | None:
        mapping = {
            settings.stripe_basic_price_id: "basic",
            settings.stripe_pro_price_id: "pro",
            settings.stripe_premium_price_id: "premium",
        }
        slug = mapping.get(price_id)
        if slug:
            plan = await self.get_by_slug(slug)
            if plan:
                return plan
        return None

    def price_id_for(self, slug: str, settings: Settings) -> str | None:
        return {
            "basic": settings.stripe_basic_price_id,
            "pro": settings.stripe_pro_price_id,
            "premium": settings.stripe_premium_price_id,
        }.get(slug)

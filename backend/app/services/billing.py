"""Apply verified Stripe events. Entitlements are granted only here, never from the frontend."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.stripe_event import StripeEvent
from app.models.subscription import Subscription
from app.models.user import User
from app.services.credits import CreditService
from app.services.plans import PlanService


def _ts(value: int | float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _obj(event: dict) -> dict:
    data = event.get("data") or {}
    obj = data.get("object") or {}
    return obj


def _price_id(obj: dict) -> str | None:
    items = (obj.get("items") or {}).get("data") or []
    if items:
        price = items[0].get("price") or {}
        return price.get("id")
    if obj.get("plan"):
        return (obj.get("plan") or {}).get("id")
    return obj.get("price_id")


class BillingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._plans = PlanService(session)
        self._credits = CreditService(session)

    async def already_processed(self, event_id: str) -> bool:
        row = await self._session.scalar(
            select(StripeEvent.id).where(StripeEvent.event_id == event_id)
        )
        return row is not None

    async def mark_processed(self, event: dict) -> None:
        self._session.add(
            StripeEvent(
                event_id=event["id"],
                event_type=event.get("type") or "",
                payload=json.dumps({"id": event.get("id"), "type": event.get("type")}),
            )
        )

    async def handle_event(self, event: dict) -> None:
        event_id = event.get("id")
        if not event_id:
            return
        if await self.already_processed(event_id):
            return
        etype = event.get("type")
        if etype == "checkout.session.completed":
            await self._checkout_completed(_obj(event))
        elif etype in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            await self._subscription_upserted(_obj(event), event_id)
        elif etype == "customer.subscription.deleted":
            await self._subscription_deleted(_obj(event))
        elif etype == "invoice.paid":
            await self._invoice_paid(_obj(event), event_id)
        elif etype == "invoice.payment_failed":
            await self._invoice_payment_failed(_obj(event))
        await self.mark_processed(event)
        await self._session.commit()

    async def _user_from_metadata(self, metadata: dict | None) -> User | None:
        user_id = (metadata or {}).get("user_id")
        if not user_id:
            return None
        try:
            uid = UUID(user_id)
        except ValueError:
            return None
        return await self._session.get(User, uid)

    async def _user_from_customer(self, customer_id: str | None) -> User | None:
        if not customer_id:
            return None
        sub = await self._session.scalar(
            select(Subscription).where(Subscription.stripe_customer_id == customer_id)
        )
        if sub is None:
            return None
        return await self._session.get(User, sub.user_id)

    async def _get_or_create_subscription(self, user: User) -> Subscription:
        sub = await self._session.scalar(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        if sub is None:
            sub = Subscription(user_id=user.id)
            self._session.add(sub)
            await self._session.flush()
        return sub

    async def _checkout_completed(self, obj: dict) -> None:
        user = await self._user_from_metadata(obj.get("metadata"))
        if user is None:
            return
        sub = await self._get_or_create_subscription(user)
        if obj.get("customer"):
            sub.stripe_customer_id = obj["customer"]
        if obj.get("subscription"):
            sub.stripe_subscription_id = obj["subscription"]
        await self._session.flush()

    async def _subscription_upserted(self, obj: dict, event_id: str) -> None:
        user = await self._user_from_metadata(obj.get("metadata"))
        if user is None:
            user = await self._user_from_customer(obj.get("customer"))
        if user is None:
            return
        sub = await self._get_or_create_subscription(user)
        sub.stripe_customer_id = obj.get("customer") or sub.stripe_customer_id
        sub.stripe_subscription_id = obj.get("id") or sub.stripe_subscription_id
        sub.status = obj.get("status") or sub.status
        price_id = _price_id(obj)
        if price_id:
            sub.stripe_price_id = price_id
        plan = None
        if price_id:
            plan = await self._plans.get_by_price_id(price_id, self._settings)
        if plan:
            sub.plan = plan.slug
            user.plan = plan.slug
        period_start = _ts(obj.get("current_period_start"))
        period_end = _ts(obj.get("current_period_end"))
        if period_start:
            sub.current_period_start = period_start
        if period_end:
            sub.current_period_end = period_end
        await self._session.flush()
        if plan and period_start and period_end and sub.status in {"active", "trialing"}:
            await self._credits.allocate_period(
                user, plan, period_start, period_end, stripe_event_id=event_id
            )

    async def _subscription_deleted(self, obj: dict) -> None:
        user = await self._user_from_customer(obj.get("customer"))
        if user is None:
            user = await self._user_from_metadata(obj.get("metadata"))
        if user is None:
            return
        sub = await self._get_or_create_subscription(user)
        sub.status = "canceled"
        user.plan = "none"
        await self._session.flush()

    async def _invoice_paid(self, obj: dict, event_id: str) -> None:
        customer = obj.get("customer")
        user = await self._user_from_customer(customer)
        if user is None:
            return
        sub = await self._get_or_create_subscription(user)
        lines = (obj.get("lines") or {}).get("data") or []
        period_start = period_end = None
        price_id = sub.stripe_price_id
        if lines:
            period = lines[0].get("period") or {}
            period_start = _ts(period.get("start"))
            period_end = _ts(period.get("end"))
            price_id = (lines[0].get("price") or {}).get("id") or price_id
        if period_start:
            sub.current_period_start = period_start
        if period_end:
            sub.current_period_end = period_end
        sub.status = "active"
        plan = None
        if price_id:
            sub.stripe_price_id = price_id
            plan = await self._plans.get_by_price_id(price_id, self._settings)
        if plan and period_start and period_end:
            await self._credits.allocate_period(
                user, plan, period_start, period_end, stripe_event_id=event_id
            )

    async def _invoice_payment_failed(self, obj: dict) -> None:
        user = await self._user_from_customer(obj.get("customer"))
        if user is None:
            return
        sub = await self._get_or_create_subscription(user)
        sub.status = "past_due"
        await self._session.flush()

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db
from app.core.db import admin_session_factory
from app.core.settings import get_settings
from app.models.user import User
from app.schemas.billing import (
    BillingSummary,
    CheckoutRequest,
    CheckoutResponse,
    CreditsSummary,
    CreditHistoryItem,
    PlanPublic,
    PortalResponse,
)
from app.services.credits import CreditService
from app.services.plans import PlanService
from app.services.stripe_gateway import get_stripe_gateway, require_stripe_connected
from sqlalchemy import select

from app.models.credit import CreditTransaction
from app.models.subscription import Subscription

router = APIRouter(prefix="/api", tags=["billing"])


@router.get("/plans", response_model=list[PlanPublic])
async def list_plans() -> list[PlanPublic]:
    factory = admin_session_factory()
    async with factory() as session:
        await PlanService(session).ensure_defaults()
        await session.commit()
        plans = await PlanService(session).list_enabled()
        return [PlanPublic.model_validate(p) for p in plans]


@router.get("/credits", response_model=CreditsSummary)
async def get_credits(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CreditsSummary:
    credits = CreditService(session)
    account = await credits.ensure_account(user.id)
    return CreditsSummary(
        available=await credits.available(user.id),
        monthly_allowance=account.monthly_allowance,
        used_this_period=await credits.used_this_period(user.id, account.current_period_start),
        rollover=await credits.rollover_available(user.id),
        period_start=account.current_period_start,
        period_end=account.current_period_end,
    )


@router.get("/credits/history", response_model=list[CreditHistoryItem])
async def credit_history(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[CreditHistoryItem]:
    rows = list(
        (
            await session.scalars(
                select(CreditTransaction)
                .where(CreditTransaction.user_id == user.id)
                .order_by(CreditTransaction.created_at.desc())
                .limit(50)
            )
        ).all()
    )
    return [CreditHistoryItem.model_validate(row) for row in rows]


@router.get("/billing", response_model=BillingSummary)
async def get_billing(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BillingSummary:
    credits = CreditService(session)
    account = await credits.ensure_account(user.id)
    plan = await PlanService(session).get_by_slug(user.plan) if user.plan != "none" else None
    sub = await session.scalar(select(Subscription).where(Subscription.user_id == user.id))
    summary = CreditsSummary(
        available=await credits.available(user.id),
        monthly_allowance=account.monthly_allowance,
        used_this_period=await credits.used_this_period(user.id, account.current_period_start),
        rollover=await credits.rollover_available(user.id),
        period_start=account.current_period_start,
        period_end=account.current_period_end,
    )
    return BillingSummary(
        plan=user.plan,
        plan_display_name=None if plan is None else plan.display_name,
        status=sub.status if sub else "none",
        amount_cents=None if plan is None else plan.amount_cents,
        currency=None if plan is None else plan.currency,
        monthly_credits=0 if plan is None else plan.monthly_credits,
        rollover_cap=0 if plan is None else plan.rollover_cap,
        credits=summary,
        stripe_enabled=get_settings().stripe_enabled,
    )


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> CheckoutResponse:
    settings = get_settings()
    factory = admin_session_factory()
    async with factory() as session:
        await PlanService(session).ensure_defaults()
        plan = await PlanService(session).get_by_slug(body.plan)
        if plan is None or not plan.enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan")
        require_stripe_connected()
        price_id = PlanService(session).price_id_for(plan.slug, settings)
        if not price_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Plan is not available for checkout",
            )
        sub = await session.scalar(select(Subscription).where(Subscription.user_id == user.id))
        customer_id = None if sub is None else sub.stripe_customer_id
        app_url = settings.public_app_url.rstrip("/")
        session_info = get_stripe_gateway().create_checkout_session(
            customer_email=user.email or "user@example.com",
            customer_id=customer_id,
            price_id=price_id,
            metadata={"user_id": str(user.id), "plan": plan.slug},
            success_url=f"{app_url}/billing?checkout=success",
            cancel_url=f"{app_url}/billing?checkout=cancel",
        )
    return CheckoutResponse(url=session_info["url"])


@router.post("/billing/portal", response_model=PortalResponse)
async def create_portal(user: Annotated[User, Depends(get_current_user)]) -> PortalResponse:
    require_stripe_connected()
    settings = get_settings()
    factory = admin_session_factory()
    async with factory() as session:
        sub = await session.scalar(select(Subscription).where(Subscription.user_id == user.id))
        if sub is None or not sub.stripe_customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No billing account yet",
            )
        customer_id = sub.stripe_customer_id
    app_url = settings.public_app_url.rstrip("/")
    portal = get_stripe_gateway().create_portal_session(
        customer_id=customer_id,
        return_url=f"{app_url}/billing",
    )
    return PortalResponse(url=portal["url"])

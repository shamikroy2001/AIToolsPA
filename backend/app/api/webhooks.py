from fastapi import APIRouter, HTTPException, Request, status

from app.core.db import admin_session_factory
from app.core.settings import get_settings
from app.services.billing import BillingService
from app.services.plans import PlanService
from app.services.stripe_gateway import get_stripe_gateway, require_stripe_connected

router = APIRouter(tags=["webhooks"])


@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict[str, str]:
    require_stripe_connected()
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    event = get_stripe_gateway().parse_event(payload, signature)
    if not event.get("id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event")
    settings = get_settings()
    factory = admin_session_factory()
    async with factory() as session:
        await PlanService(session).ensure_defaults()
        await BillingService(session, settings).handle_event(event)
    return {"status": "ok"}

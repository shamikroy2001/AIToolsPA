from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    monthly_credits: int
    rollover_cap: int
    amount_cents: int
    currency: str


class CheckoutRequest(BaseModel):
    plan: str


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class CreditsSummary(BaseModel):
    available: int
    monthly_allowance: int
    used_this_period: int
    rollover: int
    period_start: datetime | None
    period_end: datetime | None


class CreditHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_type: str
    amount: int
    description: str
    created_at: datetime


class BillingSummary(BaseModel):
    plan: str
    plan_display_name: str | None
    status: str
    amount_cents: int | None
    currency: str | None
    monthly_credits: int
    rollover_cap: int
    credits: CreditsSummary
    stripe_enabled: bool = True

"""Default plan catalog. Live amounts live in the `plans` table; env supplies Stripe Price IDs."""

from typing import TypedDict


class PlanSeed(TypedDict):
    slug: str
    display_name: str
    monthly_credits: int
    rollover_cap: int
    rollover_expiry_days: int
    amount_cents: int
    currency: str
    sort_order: int


DEFAULT_PLANS: list[PlanSeed] = [
    {
        "slug": "basic",
        "display_name": "Basic",
        "monthly_credits": 1000,
        "rollover_cap": 1000,
        "rollover_expiry_days": 90,
        "amount_cents": 999,
        "currency": "usd",
        "sort_order": 1,
    },
    {
        "slug": "pro",
        "display_name": "Pro",
        "monthly_credits": 5000,
        "rollover_cap": 5000,
        "rollover_expiry_days": 90,
        "amount_cents": 2499,
        "currency": "usd",
        "sort_order": 2,
    },
    {
        "slug": "premium",
        "display_name": "Premium",
        "monthly_credits": 15000,
        "rollover_cap": 15000,
        "rollover_expiry_days": 90,
        "amount_cents": 4999,
        "currency": "usd",
        "sort_order": 3,
    },
]

"""Stripe gateway. Tests inject FakeStripeGateway — never call live Stripe in pytest."""

from __future__ import annotations

import json
from typing import Any, Protocol

from fastapi import HTTPException, status

from app.core.settings import Settings, get_settings


class StripeGateway(Protocol):
    def create_checkout_session(
        self,
        *,
        customer_email: str,
        customer_id: str | None,
        price_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]: ...

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict[str, str]: ...

    def parse_event(self, payload: bytes, signature: str | None) -> dict[str, Any]: ...


class StripeApiGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self):
        if not self._settings.stripe_secret_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Billing is not configured",
            )
        import stripe

        stripe.api_key = self._settings.stripe_secret_key
        return stripe

    def create_checkout_session(
        self,
        *,
        customer_email: str,
        customer_id: str | None,
        price_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        stripe = self._client()
        kwargs: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
        }
        if customer_id:
            kwargs["customer"] = customer_id
        else:
            kwargs["customer_email"] = customer_email
        session = stripe.checkout.Session.create(**kwargs)
        return {"id": session.id, "url": session.url}

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict[str, str]:
        stripe = self._client()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"url": session.url}

    def parse_event(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        if not self._settings.stripe_webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Billing is not configured",
            )
        stripe = self._client()
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature or "",
                self._settings.stripe_webhook_secret,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            ) from exc
        if hasattr(event, "to_dict"):
            return event.to_dict()
        return dict(event)


class FakeStripeGateway:
    def __init__(self) -> None:
        self.checkouts: list[dict[str, Any]] = []
        self.portals: list[dict[str, Any]] = []

    def create_checkout_session(
        self,
        *,
        customer_email: str,
        customer_id: str | None,
        price_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        record = {
            "customer_email": customer_email,
            "customer_id": customer_id,
            "price_id": price_id,
            "metadata": metadata,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        self.checkouts.append(record)
        return {"id": f"cs_test_{len(self.checkouts)}", "url": "https://stripe.test/checkout"}

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict[str, str]:
        self.portals.append({"customer_id": customer_id, "return_url": return_url})
        return {"url": "https://stripe.test/portal"}

    def parse_event(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        del signature
        return json.loads(payload.decode("utf-8"))


def require_stripe_connected() -> None:
    """Stripe code stays in-tree; staging can leave it dormant via STRIPE_ENABLED=false."""
    if not get_settings().stripe_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is paused. Stripe is disconnected for this environment.",
        )


_gateway: StripeGateway | None = None


def set_stripe_gateway(gateway: StripeGateway | None) -> None:
    global _gateway
    _gateway = gateway


def get_stripe_gateway() -> StripeGateway:
    if _gateway is not None:
        return _gateway
    return StripeApiGateway(get_settings())

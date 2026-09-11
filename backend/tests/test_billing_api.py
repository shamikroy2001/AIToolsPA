"""Billing HTTP + webhooks. FakeStripeGateway — no live Stripe."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.settings import clear_settings_cache
from conftest import TOKEN_A, TOKEN_B


def _auth(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _period_ts():
    start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
    return start, end


def test_plans_are_public(saas_client: TestClient):
    response = saas_client.get("/api/plans")
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.json()}
    assert slugs == {"basic", "pro", "premium"}
    pro = next(row for row in response.json() if row["slug"] == "pro")
    assert pro["monthly_credits"] == 5000
    assert "stripe_price_id" not in pro


def test_checkout_does_not_grant_credits(saas_client: TestClient, fake_stripe):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/billing/checkout", json={"plan": "pro"}, headers=_auth())
    assert response.status_code == 200
    assert response.json()["url"] == "https://stripe.test/checkout"
    credits = saas_client.get("/api/credits", headers=_auth())
    assert credits.json()["available"] == 0
    assert fake_stripe.checkouts[0]["price_id"] == "price_pro"
    assert "user_id" in fake_stripe.checkouts[0]["metadata"]


def test_subscription_webhook_allocates_and_is_idempotent(saas_client: TestClient):
    me = saas_client.get("/api/me", headers=_auth()).json()
    start, end = _period_ts()
    event = {
        "id": "evt_sub_1",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "active",
                "current_period_start": start,
                "current_period_end": end,
                "items": {"data": [{"price": {"id": "price_pro"}}]},
                "metadata": {"user_id": me["id"]},
            }
        },
    }
    first = saas_client.post("/api/webhooks/stripe", json=event)
    second = saas_client.post("/api/webhooks/stripe", json=event)
    assert first.status_code == 200
    assert second.status_code == 200
    credits = saas_client.get("/api/credits", headers=_auth()).json()
    assert credits["available"] == 5000
    billing = saas_client.get("/api/billing", headers=_auth()).json()
    assert billing["plan"] == "pro"
    assert billing["credits"]["available"] == 5000


def test_user_cannot_see_other_credits(saas_client: TestClient):
    me_a = saas_client.get("/api/me", headers=_auth(TOKEN_A)).json()
    saas_client.get("/api/me", headers=_auth(TOKEN_B))
    start, end = _period_ts()
    event = {
        "id": "evt_only_a",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_a",
                "customer": "cus_a",
                "status": "active",
                "current_period_start": start,
                "current_period_end": end,
                "items": {"data": [{"price": {"id": "price_pro"}}]},
                "metadata": {"user_id": me_a["id"]},
            }
        },
    }
    saas_client.post("/api/webhooks/stripe", json=event)
    credits_a = saas_client.get("/api/credits", headers=_auth(TOKEN_A)).json()
    credits_b = saas_client.get("/api/credits", headers=_auth(TOKEN_B)).json()
    assert credits_a["available"] == 5000
    assert credits_b["available"] == 0


def test_payment_failed_marks_past_due(saas_client: TestClient):
    me = saas_client.get("/api/me", headers=_auth()).json()
    start, end = _period_ts()
    saas_client.post(
        "/api/webhooks/stripe",
        json={
                "id": "evt_ok",
                "type": "customer.subscription.created",
                "data": {
                    "object": {
                        "id": "sub_1",
                        "customer": "cus_1",
                        "status": "active",
                        "current_period_start": start,
                        "current_period_end": end,
                        "items": {"data": [{"price": {"id": "price_pro"}}]},
                        "metadata": {"user_id": me["id"]},
                    }
                },
            },
    )
    saas_client.post(
        "/api/webhooks/stripe",
        json={
                "id": "evt_fail",
                "type": "invoice.payment_failed",
                "data": {"object": {"customer": "cus_1"}},
            },
    )
    billing = saas_client.get("/api/billing", headers=_auth()).json()
    assert billing["status"] == "past_due"


def test_portal_requires_customer(saas_client: TestClient):
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/billing/portal", headers=_auth())
    assert response.status_code == 400


def test_stripe_dormant_blocks_checkout_and_webhooks(saas_client: TestClient, monkeypatch):
    monkeypatch.setenv("STRIPE_ENABLED", "false")
    clear_settings_cache()
    saas_client.get("/api/me", headers=_auth())
    checkout = saas_client.post("/api/billing/checkout", json={"plan": "pro"}, headers=_auth())
    assert checkout.status_code == 503
    assert "paused" in checkout.json()["detail"].lower()
    webhook = saas_client.post("/api/webhooks/stripe", json={"id": "evt_ignored"})
    assert webhook.status_code == 503
    billing = saas_client.get("/api/billing", headers=_auth()).json()
    assert billing["stripe_enabled"] is False
    health = saas_client.get("/health").json()
    assert health["billing"] == "dormant"
    monkeypatch.delenv("STRIPE_ENABLED", raising=False)
    clear_settings_cache()

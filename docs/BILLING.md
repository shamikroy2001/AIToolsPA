# Billing

Stripe is the source of subscription truth when `STRIPE_ENABLED=true`. The frontend never grants entitlements.

**Current staging: Stripe is dormant.** Checkout, Customer Portal, and webhooks return 503. Gateway and ledger code stay in the repo. Re-enable by setting `STRIPE_ENABLED=true` plus test-mode keys and Price IDs.

## D1

- Configurable plans: Basic / Pro / Premium (example $9.99 / $24.99 / $49.99 — stored in `plans` + Stripe Price IDs in env)
- Checkout for new subscriptions
- Customer Portal for manage/cancel
- Webhooks (verified, idempotent): `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.paid`, `invoice.payment_failed`
- On period start: monthly allocation + capped rollover (see CREDITS.md)
- Insufficient credits in D1: upgrade CTA only (no top-up SKUs yet)

## D2

- Credit top-up packs (configurable amounts/prices)
- Checkout → webhook → `TOPUP` lot (never on client “success”)
- Usage warnings at 75% / 90% / 100%
- No automatic extra charges without Checkout

Webhook processing is transactional and logged without storing secrets.

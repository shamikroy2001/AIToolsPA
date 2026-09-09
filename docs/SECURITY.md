# Security

Production-critical. D1 establishes the baseline; D2 hardens.

## Always

- Clerk on every product API; reject anonymous access except health, webhooks, auth callbacks
- Tenant filter + RLS session variable
- Secrets only in server env / Railway / Vercel (publishable Clerk key is the exception)
- No AI keys in the frontend
- Stripe webhook signature verification + idempotency
- Pydantic validation, rate limits (D1 basic, D2 tighter)
- Structured logs with request/user/task ids; never OAuth tokens, API keys, raw email bodies

## D2

- Encrypted integration credentials at rest
- Gmail refresh tokens never sent to the browser
- Telegram credentials isolated per user
- Admin routes require an allowlisted Clerk org/role
- Audit log for billing and credit adjustments
- Explicit cross-user penetration tests in CI

Gmail: request minimum OAuth scopes; product copy distinguishes read-only vs send.

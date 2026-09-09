# Architecture

Personal Assistant is a multi-tenant product. Customers never see AI providers, model names, tokens, or gateway configuration.

```
Next.js (Vercel)
    → FastAPI (Railway)
        → Clerk (identity)
        → CreditService + lots/ledger (Supabase Postgres)
        → Assistant engine
            → AIRouter
                → Vercel AI Gateway
                    → internal models
        → Arq workers (Railway) + Redis
```

## Releases

- **D1 Core Platform staging:** auth, tenancy, subscriptions, monthly credits + rollover, assistant profile, happy-path AI ask, dashboard.
- **D2 Automation staging:** Gmail, Telegram, website monitors, real scheduled jobs, top-ups, fallback routing, admin usage/cost, hardening.
- **Production:** after D2 acceptance. Not combined with D1.

## Locked infrastructure

- Workers: Arq + Redis
- API + worker host: Railway (two processes: `uvicorn`, `arq`)
- Frontend: Vercel
- Database: Supabase PostgreSQL
- Auth: Clerk (no custom auth)
- Billing: Stripe Checkout, Customer Portal, webhooks (never trust the browser)

## Tenant isolation

Every customer row has `user_id`. FastAPI sets `SET LOCAL app.user_id` and still filters in queries. RLS is defense in depth. Workers receive `user_id` in the job payload. Cross-user access is tested before D1 staging.

## Service boundaries

`AuthService`, `BillingService`, `CreditService`, `AssistantService`, `TaskService`, `AIRouter`, `AIUsageService`, `GmailService`, `TelegramService`, `WebsiteMonitorService`, `NotificationService`, `SchedulerService`.

`AIRouter` does not know about Stripe. `CreditService` does not know about providers.

## Current repo note

`backend/src/assistant` is the legacy SQLite task CLI. It is not the SaaS data plane. D1 uses SQLAlchemy + Alembic on Postgres.

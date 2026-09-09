# D1 staging freeze

This is the **Core Platform** staging release. D2 (Gmail, Telegram, monitors, top-ups, fallback models, admin analytics) is out of scope until this freeze is accepted.

`/health` reports `"release": "D1-staging"`.

## In scope

- Clerk sign-in / sign-up
- Next.js on Vercel talking to FastAPI on Railway
- Supabase Postgres + Alembic through `0003_assistant_ai`
- Tenant isolation (`user_id` + RLS) for profiles, tasks, credits
- Stripe **test** Checkout, Customer Portal, webhooks → monthly credits + rollover
- Assistant profile + ask (`assistant_ask`, 5 credits)
- AIRouter → Vercel AI Gateway (server-only)
- Arq worker: `ping` + daily credit lot expiry
- Customer UI never shows provider, model, tokens, or API keys

## Out of scope (do not build or enable)

- Gmail, Telegram, website monitors, user schedules
- Credit top-up packs
- AI fallback routes
- Admin usage/cost UI
- Production Stripe / production Clerk instance
- Promoting this environment to production

## Frozen acceptance

1. `GET /health` → `release` is `D1-staging`
2. Sign in with Clerk; `GET /api/me` upserts the user
3. Pricing / Checkout in Stripe test; webhook allocates monthly credits (not the success URL)
4. Dashboard shows available credits; ask returns a reply and deducts 5 credits
5. A second Clerk user cannot read the first user's tasks or credits
6. 402 when credits are 0, with upgrade copy — no AI call
7. Network tab / JSON has no `provider`, `model`, or `tokens`
8. Worker cron is attached (Redis); API and worker share `REDIS_URL`
9. Stripe CLI or Dashboard shows signed webhooks succeeding
10. CI green: backend pytest + frontend `next build`

## Operator steps (you must apply secrets)

This repo cannot create your Railway / Vercel / Supabase / Clerk / Stripe projects.

1. **Supabase:** new project. SQL editor: create `pa_app` from `infrastructure/supabase/bootstrap.sql` (change the password). Use **direct** or **session** pooler URLs, not transaction pooler if you hit RLS/session issues.
2. **Railway API:** Root Directory `backend`. Env from `.env.staging.example`. `DATABASE_ADMIN_URL` is the postgres role (migrations + webhooks). `DATABASE_URL` is `pa_app`. First deploy runs `alembic upgrade head`.
3. **Re-run GRANTs** in the bootstrap file after the first successful migrate.
4. **Railway Redis** plugin. Copy `REDIS_URL` to API and worker.
5. **Railway worker:** same image, start command `arq app.workers.arq_worker.WorkerSettings`. Same DB admin URL + Redis. No Gmail env.
6. **Vercel:** Root `frontend`. Env from `frontend/.env.example`. `NEXT_PUBLIC_API_URL` is the public Railway HTTPS origin (no trailing slash).
7. **Clerk:** staging instance. Allowed origins = Vercel URL. JWT issuer / JWKS match Railway `CLERK_ISSUER` / `CLERK_JWKS_URL`.
8. **Stripe test:** three recurring Prices mapped to Basic / Pro / Premium. Webhook `https://<api>/api/webhooks/stripe` for `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`. Signing secret → `STRIPE_WEBHOOK_SECRET`.
9. **AI Gateway:** key and route model IDs on Railway only.
10. Confirm CORS: `PUBLIC_APP_URL` and `CORS_ORIGINS` equal the Vercel origin.

Do not start D2 work until this list is checked off in staging.

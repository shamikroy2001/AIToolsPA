# D1 staging freeze

This is the **Core Platform** staging release. D2 (Gmail, Telegram, monitors, top-ups, fallback models, admin analytics) is out of scope until this freeze is accepted.

`/health` reports `"release": "D1-staging"`.

## In scope

- Clerk sign-in / sign-up
- Next.js on Vercel talking to FastAPI on Railway
- Supabase Postgres + Alembic through `0003_assistant_ai`
- Tenant isolation (`user_id` + RLS) for profiles, tasks, credits
- Stripe code is **in the repo but dormant** (`STRIPE_ENABLED=false`); no Checkout, Portal, or webhooks until re-enabled
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

1. `GET https://aitoolspa-production-108b.up.railway.app/health` → `release` is `D1-staging`
2. Sign in with Clerk; `GET /api/me` upserts the user
3. Pricing catalog loads; Checkout/Portal return paused while Stripe is dormant
4. Dashboard shows available credits; ask returns a reply and deducts 5 credits (needs a credit grant path — not Stripe while dormant)
5. A second Clerk user cannot read the first user's tasks or credits
6. 402 when credits are 0, with upgrade copy — no AI call
7. Network tab / JSON has no `provider`, `model`, or `tokens`
8. Worker cron is attached (Redis); API and worker share `REDIS_URL`
9. Stripe webhook endpoint stays deployed but returns 503 while dormant
10. CI green: backend pytest + frontend `next build`

## Operator steps (you must apply secrets)

This repo cannot create your Railway / Vercel / Supabase / Clerk / Stripe projects.

1. **Supabase:** new project. SQL editor: create `pa_app` from `infrastructure/supabase/bootstrap.sql` (change the password). Use **direct** or **session** pooler URLs, not transaction pooler if you hit RLS/session issues. On Railway set `SUPABASE_URL` plus `SUPABASE_PUBLISHABLE_KEY` and/or `SUPABASE_SECRET_KEY` (`sb_…` keys from Settings → API Keys). Do not put those keys on Vercel. `/health` reports `supabase` as `ok` when the Data API accepts the key. Alembic and RLS still use `DATABASE_URL`.
2. **Railway API:** leave Root Directory **empty**. Start command `python start_api.py` (overrides any dashboard `uvicorn main:app`). Attach the public `*.up.railway.app` domain to this API service, not the worker. Env from `.env.staging`. `DATABASE_ADMIN_URL` is the postgres role. `DATABASE_URL` is `pa_app`.
3. **Re-run GRANTs** in the bootstrap file after the first successful migrate.
4. **Railway Redis** plugin. Copy `REDIS_URL` to API and worker.
5. **Railway worker:** Dockerfile `Dockerfile.worker`. Start command **must** be `python -m arq app.workers.arq_worker.WorkerSettings` — not the API `alembic`/`uvicorn` command. Same `REDIS_URL` and `DATABASE_ADMIN_URL`. No Gmail env.
6. **Vercel:** Root `frontend`. Env from `frontend/.env.example`. `NEXT_PUBLIC_API_URL=https://aitoolspa-production-108b.up.railway.app` (no trailing slash).
7. **Clerk:** staging instance. Allowed origins = Vercel URL. JWT issuer / JWKS match Railway `CLERK_ISSUER` / `CLERK_JWKS_URL`.
8. **Stripe:** leave dormant. Set `STRIPE_ENABLED=false` and do not configure Price IDs or webhooks until billing is turned back on.
9. **AI Gateway:** key and route model IDs on Railway only.
10. Confirm CORS: `PUBLIC_APP_URL` and `CORS_ORIGINS` equal the Vercel origin.

### POST /api/tasks 503 after profile GET works (credit_transactions timestamptz)

After PR #5, `GET /api/me/assistant` is 200. `POST /api/tasks` then failed in `CreditService.reserve` **before the AI call** with JSON 503 (CORS ok) and no debit:

```
asyncpg.exceptions.DataError: can't subtract offset-naive and offset-aware datetimes
INSERT INTO credit_transactions (..., created_at) VALUES (..., $9::TIMESTAMP WITHOUT TIME ZONE)
```

`utc_now()` is timezone-aware. The ORM mapped `created_at` as naive `DateTime`, so asyncpg bound `TIMESTAMP WITHOUT TIME ZONE`. Alembic `0002` created `timestamptz`. The models now use `DateTime(timezone=True)`; Alembic `0007_credit_timestamptz` converts any leftover naive columns on `credit_*`, `subscriptions`, `stripe_events`, and assistant task/usage timestamps.

### GET/PATCH /api/me/assistant and POST /api/tasks 500 while D2 GETs work

Confirmed on live Railway HTTP logs (staging still on `main` `60a3905`), not only the older `task_costs` INSERT theory. Operator disabled RLS on `task_costs` and seeded `assistant_ask`; ask still 500s.

| Route | Live result |
| --- | --- |
| `GET /api/me`, `/api/credits`, `/api/plans`, `/api/monitors`, `/api/integrations` | 200 |
| `GET /api/me/assistant` | 500 (~350–500ms) |
| `PATCH /api/me/assistant` | 500 |
| `POST /api/tasks` | 500 (same latency; no debit) |

On `main`, GET/PATCH/ask all call `get_or_create_profile`, which **INSERTs `assistant_profiles` as `pa_app`**. That handler never touches `task_costs` or the AI gateway. Two write failures:

1. **Schema vs model.** Alembic `0003` created `created_at` / `updated_at` as `timestamptz`. The ORM used naive `DateTime` + aware `utc_now()` — the same asyncpg bind error that previously broke `users` / `plans`. The model now uses `DateTime(timezone=True)`. The `timezone` column is quoted.
2. **RLS / GRANT.** `ENABLE` + `FORCE ROW LEVEL SECURITY` without `{table}_tenant` denies tenant INSERT. Admin upserts now set `app.user_id`.

`GET /api/me/assistant` is now **read-only** (defaults if the row is missing or unreadable). PATCH/ask persist via admin + `app.user_id` and return in-memory values if persist is denied. Ask does not call `get_or_create_profile`.

Optional paste: `infrastructure/supabase/assistant_rls.sql` (or Alembic `0006_assistant_profile_rls`). Clerk session JWTs from this app expire in ~60 seconds — mint a fresh token immediately before a live curl.

### POST /api/tasks 500 while /api/me and /api/credits work

`task_costs` and `plans` are catalog tables (no `user_id`). If RLS is enabled on them without a `SELECT` policy, `pa_app` sees zero cost rows. Older API builds then tried to INSERT `task_costs` (GRANT is SELECT-only) and returned an opaque `text/plain` 500 without CORS.

The API no longer writes `task_costs` on the ask path (defaults to 5 credits). Alembic `0005_catalog_rls` and a re-run of `infrastructure/supabase/bootstrap.sql` add `task_costs_read` / `plans_read`. Optional paste if you cannot wait for migrate:

```sql
ALTER TABLE task_costs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS task_costs_read ON task_costs;
CREATE POLICY task_costs_read ON task_costs FOR SELECT USING (true);
GRANT SELECT ON TABLE task_costs TO pa_app;

INSERT INTO task_costs (id, task_type, base_credit_cost, minimum_cost, maximum_cost, enabled)
VALUES (gen_random_uuid(), 'assistant_ask', 5, 1, 20, true)
ON CONFLICT (task_type) DO UPDATE SET enabled = true, base_credit_cost = 5;
```

`AI_GATEWAY_API_KEY` and `AI_GATEWAY_BASE_URL` stay on Railway only. Unhandled errors return JSON `{"detail": "..."}` (never Starlette's 21-byte `text/plain` `Internal Server Error`). Tracebacks go to `app.errors` and stderr so Railway deploy logs show them even after Alembic `fileConfig`.

A `POST /api/tasks` 500 with no Python traceback on Railway was caused by Alembic migrate-on-boot calling `logging.config.fileConfig` with `disable_existing_loggers=True` (the default), which silenced `uvicorn.error`. That is now `False`, and `start_api` re-enables app loggers after migrate.

Do not start D2 work until this list is checked off in staging.

## D2 Slice 2 (APIs; release stays D1-staging)

Catalog, monitors, schedules, and notifications APIs plus Connections / Monitoring pages.

- No new Railway or Vercel secrets.
- `POST /api/integrations/gmail/connect` and Telegram connect return 503 until OAuth env exists. Real OAuth is a later slice.
- Worker registers `poll_due_monitors` as a no-op cron so Arq is proven. Real hash-check polling comes next.
- Leave `/health` `release` as `D1-staging` until these APIs are proven on staging. Do not enable Stripe.

## D2 Slice 3 (monitor worker; release stays D1-staging)

`poll_due_monitors` hash-checks enabled website monitors every 15 minutes. No Google/Telegram env.

- **Due monitors:** `enabled` and `last_checked_at` is null or older than 15 minutes.
- **HTTP:** GET with a 10s timeout and `AIToolsPA-Monitor/1.0` user-agent. Body is SHA-256 hashed (first 1 MB).
- **First check:** stores `last_hash` as a baseline. No notification.
- **Change:** updates `last_hash` / `last_changed_at` / `last_checked_at` and writes an `in_app` notification. No hashes or credentials in the payload.
- **No change:** updates `last_checked_at` only. Still charges (the check is the billed work).
- **Credits:** `task_costs.website_monitor` (base 3). Charged only after a successful GET via `CreditService.consume`. Insufficient credits **fail soft**: that monitor is skipped (no fetch, no notify, `last_checked_at` unchanged) and other monitors still run. HTTP failures also skip charge and leave `last_checked_at` unset so the next cron retries.
- **Tenancy:** admin session lists due rows; each write sets `app.user_id` before mutating that user's monitor/credits/notification.
- **Schedules:** `gmail_analyze` / `telegram_notify` / `assistant_ask` are skipped and stay due. A `website_monitor` schedule only advances `next_run_at` — the actual fetch is the monitor row poll.
- **Railway worker** may not exist yet in `dazzling-transformation`. Add a second service with Dockerfile `Dockerfile.worker` and start command `python -m arq app.workers.arq_worker.WorkerSettings`. Same `REDIS_URL` and `DATABASE_ADMIN_URL` as D1. Do not run Alembic on the worker. Do not add Gmail/Telegram secrets.
- Leave `/health` `release` as `D1-staging`. Do not enable Stripe.

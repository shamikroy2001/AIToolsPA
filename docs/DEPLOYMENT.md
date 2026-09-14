# Deployment

## D0 (local)

```bash
docker compose up postgres redis
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## D1 staging freeze

The freeze contract, in/out of scope, and acceptance list live in [STAGING.md](STAGING.md). Env templates: `.env.staging.example` (Railway) and `frontend/.env.example` (Vercel).

1. Supabase Postgres. Create `pa_app`, then let the API run Alembic (`0001`–`0003`). Re-apply GRANTs from `infrastructure/supabase/bootstrap.sql`. Railway also needs `SUPABASE_URL` and `sb_publishable_` / `sb_secret_` API keys (server-only).
2. Railway **API**: leave **Root Directory empty**. Dockerfile at repo root. Start command `python start_api.py` (binds Railway `$PORT` in-process). Health `https://aitoolspa-production-108b.up.railway.app/health`.
3. Railway **worker**: Dockerfile `Dockerfile.worker`, start `python -m arq app.workers.arq_worker.WorkerSettings`. Do not run Alembic on this service.
4. Railway Redis; `REDIS_URL` on API and worker. Worker also needs `DATABASE_ADMIN_URL`.
5. Vercel `frontend/`. `NEXT_PUBLIC_API_URL=https://aitoolspa-production-108b.up.railway.app`. Only Clerk **publishable** key in Next.js.
6. Stripe is **dormant** (`STRIPE_ENABLED=false`). Do not point a live webhook at staging until you re-enable it.
7. Vercel AI Gateway secrets on Railway only.
8. Stop. Do not add Gmail/Telegram/top-ups until D2 staging.

Supabase URLs may be pasted as `postgres://...`; the API rewrites them to `postgresql+asyncpg://` and uses SSL off-localhost.

## D2 staging

Slice 2 (catalog / monitors / schedules / notifications) deploys with existing env. Slice 3 adds real Arq monitor polling. Slice 4 adds Gmail/Telegram connect when optional env is set; without it, connect stays 503. Slice 5 runs due `gmail_analyze` / `telegram_notify` jobs on the worker. `/health` stays `D1-staging` until the operator accepts a D2 release label.

**Railway worker (required for Slice 3 polling):** the `dazzling-transformation` project currently has the API service only. Add a worker service when you want checks to run in staging:

1. New Railway service, **Root Directory empty**.
2. Dockerfile path: `Dockerfile.worker`.
3. Start command: `python -m arq app.workers.arq_worker.WorkerSettings` (also in `railway.worker.toml`).
4. Env: `REDIS_URL` (same as API), `DATABASE_ADMIN_URL` (postgres/service role), `DATABASE_URL` (`pa_app` is fine if present). Do **not** run Alembic here.
5. Slice 3 did not need Gmail/Telegram secrets. Slice 5 does — copy them from the API (see below).

Cron on the worker: `expire_credit_lots` daily at 03:15 UTC; `poll_due_monitors` at minute 0/15/30/45.

**Slice 4 operator (API service only, optional):**

1. Create a Google OAuth **Web** client. Authorized redirect URI: `https://aitoolspa-production-108b.up.railway.app/api/integrations/gmail/callback` (or your current Railway API host). Scope used by the app: `gmail.readonly` + `openid` + `email` (no send/modify).
2. Railway API: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI` (same callback URL), `CREDENTIAL_ENCRYPTION_KEY` (Fernet), optional `PUBLIC_API_URL`.
3. Telegram: create a bot with BotFather; set `TELEGRAM_BOT_TOKEN` on the API. Customers connect with their chat ID. The bot token never goes to the browser.
4. Leave values empty to keep connect paused (503). Never put these on Vercel or in the repo.
5. Stripe stays dormant. Do not invent a production Clerk/Stripe cutover.

**Slice 5 operator (worker service — copy API secrets, do not invent values):**

The worker in Railway project `proactive-hope` now decrypts stored integrations and calls Gmail/Telegram. Copy these from the API service onto the **worker** as well:

- `CREDENTIAL_ENCRYPTION_KEY` (must be identical to the API or decrypt fails and schedules stay due)
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` (token refresh; `GMAIL_REDIRECT_URI` is not required here)
- `TELEGRAM_BOT_TOKEN` (send to the stored chat id)

Keep `REDIS_URL` and `DATABASE_ADMIN_URL`. Do not run Alembic on the worker. Missing worker secrets fail soft (schedule stays due); they do not crash the cron.

Same hosts. Later slices can add `assistant_ask` schedules, worker concurrency, and an admin allowlist. Then production cutover after acceptance.

## Production

- Separate Stripe live keys, Clerk production instance, Supabase production.
- Current plan: production after D2, not after this D1 freeze.

Railway root: repository root (`Dockerfile` copies `backend/`). Vercel root: `frontend/`.

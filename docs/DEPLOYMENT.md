# Deployment

## D0 (local)

```bash
docker compose up postgres redis
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## D1 staging freeze

The freeze contract, in/out of scope, and acceptance list live in [STAGING.md](STAGING.md). Env templates: `.env.staging.example` (Railway) and `frontend/.env.example` (Vercel).

1. Supabase Postgres. Create `pa_app`, then let the API run Alembic (`0001`–`0003`). Re-apply GRANTs from `infrastructure/supabase/bootstrap.sql`.
2. Railway **API**: leave **Root Directory empty** (Git repo root). Uses the root `Dockerfile`, which copies `backend/`. Health `/health`. Start is `python -m alembic upgrade head && python -m uvicorn app.main:app`. If Root Directory is `backend`, use `backend/Dockerfile` instead — do not point Dockerfile at `backend/Dockerfile` while the context is the repo root (COPY of `pyproject.toml` fails).
3. Railway **worker**: Dockerfile `Dockerfile.worker`, start `python -m arq app.workers.arq_worker.WorkerSettings`. Do not run Alembic on this service.
4. Railway Redis; `REDIS_URL` on API and worker. Worker also needs `DATABASE_ADMIN_URL`.
5. Vercel `frontend/`. `NEXT_PUBLIC_API_URL` = Railway API. Only Clerk **publishable** key in Next.js.
6. Stripe is **dormant** (`STRIPE_ENABLED=false`). Do not point a live webhook at staging until you re-enable it.
7. Vercel AI Gateway secrets on Railway only.
8. Stop. Do not add Gmail/Telegram/top-ups until D2 staging.

Supabase URLs may be pasted as `postgres://...`; the API rewrites them to `postgresql+asyncpg://` and uses SSL off-localhost.

## D2 staging

Same hosts. Add Google OAuth redirect URLs, Telegram bot token, worker concurrency, admin allowlist. Then production cutover after acceptance.

## Production

- Separate Stripe live keys, Clerk production instance, Supabase production.
- Current plan: production after D2, not after this D1 freeze.

Railway root: repository root (`Dockerfile` copies `backend/`). Vercel root: `frontend/`.

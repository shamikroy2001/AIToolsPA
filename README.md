# Personal Assistant

Multi-tenant SaaS: each customer gets a customizable personal assistant. AI providers and model names are **internal only** — customers subscribe to the assistant, not to a model marketplace.

**Current freeze: D1 Core Platform staging.** D2 is a separate staging release. Do not mix them.

| Release | What ships |
|---|---|
| **D1-staging** (now) | Clerk, Vercel, Railway, Supabase, Stripe test subscriptions, credit ledger + rollover, assistant profile, ask via Gateway, dashboard |
| **D2 Automation** | Gmail, Telegram, website monitoring, scheduled jobs, top-ups, fallback routing, admin analytics, hardening |
| **Production** | After D2 acceptance |

Staging operator checklist: [docs/STAGING.md](docs/STAGING.md).

## Local development

```bash
git clone <repo>
cd gemini-personal-agent   # GitHub folder name may still be the clone; package is personal-assistant

cp .env.example .env
docker compose up postgres redis

# API
cd backend
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000

# Worker
arq app.workers.arq_worker.WorkerSettings

# Web
cd ../frontend
npm install
npm run dev
```

- API health: http://localhost:8000/health (`release` is `D1-staging`)
- Web: http://localhost:3000

## Layout

```
frontend/          Next.js (Vercel)
backend/           FastAPI + Arq (Railway)
docs/              Architecture of record
infrastructure/    Railway notes + Supabase bootstrap
docker-compose.yml Postgres + Redis + API + worker
```

## Product language

Use: Assistant, Credits, Tasks, Connections, Monitoring.

Never in the customer UI: model, tokens, provider, API key, temperature, LLM, BYOK.

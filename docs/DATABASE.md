# Database

D1 uses Supabase PostgreSQL + Alembic. Legacy SQLite (`tasks` only) remains for the old CLI and is not the SaaS schema.

All tenant tables include `user_id` (Clerk-mapped internal id).

Planned tables (D1 unless noted):

- `users` — clerk_user_id, email, plan, status
- `subscriptions` — Stripe ids, period bounds, status
- `plans` — slug, display price, monthly_credits, rollover_cap (amounts not hard-coded in UI)
- `task_costs` — task_type, base/min/max credits, enabled (catalog; `pa_app` SELECT only; never INSERT from the tenant ask path)
- `assistant_profiles` — name, personality, response_style, timezone (quoted), language; `timestamptz` created/updated. Upserted with the admin role **and** `app.user_id` so FORCE RLS WITH CHECK passes. Tenant ask does not INSERT this row.
- `credit_accounts` — period bounds, allowance, rollover_cap snapshot
- `credit_lots` — source, original/remaining, expires_at, billing_period
- `credit_transactions` — immutable ledger; types include MONTHLY_ALLOCATION, ROLLOVER, AI_USAGE, TOPUP (D2), REFUND, ADMIN_ADJUSTMENT, EXPIRATION, RESERVATION, RELEASE
- `assistant_tasks` — type, status, input/output, credits reserved/charged
- `ai_usage` — provider, model, tokens, actual_cost (admin-only; never customer APIs)
- `stripe_events` — webhook idempotency keys
- D2: `integrations`, `scheduled_tasks`, `monitored_websites`, `notifications`

RLS policies use `current_setting('app.user_id', true)`. Service role is limited to webhooks, admin, and workers that set tenant context explicitly.

`plans` and `task_costs` are not tenant-scoped. If RLS is enabled on them, they need a `FOR SELECT USING (true)` policy (`0005_catalog_rls` / `infrastructure/supabase/bootstrap.sql`). Do not add a `user_id` policy — those columns do not exist.

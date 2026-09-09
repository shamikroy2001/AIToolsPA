-- D1 staging: run in the Supabase SQL editor as the postgres role.
-- 1) Create the RLS-bound app role (set a strong password; store it in Railway DATABASE_URL).
-- 2) After `alembic upgrade head` (API boot does this), run the GRANT block.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
    CREATE ROLE pa_app LOGIN PASSWORD 'change-me-before-staging';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO pa_app;
GRANT USAGE ON SCHEMA public TO pa_app;

-- Re-run after migrations so GRANTs are not skipped when pa_app was created late.
GRANT SELECT, UPDATE ON TABLE users TO pa_app;
GRANT SELECT ON TABLE plans, task_costs TO pa_app;
GRANT SELECT, INSERT, UPDATE ON TABLE
  subscriptions,
  credit_accounts,
  credit_lots,
  credit_transactions,
  assistant_profiles,
  assistant_tasks,
  ai_usage
TO pa_app;

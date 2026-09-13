-- Staging: run in the Supabase SQL editor as the postgres role.
-- 1) Create the RLS-bound app role (set a strong password; store it in Railway DATABASE_URL).
-- 2) After the API has created tables, run this file again so GRANTs apply.
-- D2 tables are granted only if they exist.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
    CREATE ROLE pa_app LOGIN PASSWORD 'change-me-before-staging';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO pa_app;
GRANT USAGE ON SCHEMA public TO pa_app;

DO $$
DECLARE
  t text;
  privileges text;
BEGIN
  FOR t, privileges IN
    SELECT * FROM (VALUES
      ('users', 'SELECT, UPDATE'),
      ('plans', 'SELECT'),
      ('task_costs', 'SELECT'),
      ('subscriptions', 'SELECT, INSERT, UPDATE'),
      ('credit_accounts', 'SELECT, INSERT, UPDATE'),
      ('credit_lots', 'SELECT, INSERT, UPDATE'),
      ('credit_transactions', 'SELECT, INSERT, UPDATE'),
      ('assistant_profiles', 'SELECT, INSERT, UPDATE'),
      ('assistant_tasks', 'SELECT, INSERT, UPDATE'),
      ('ai_usage', 'SELECT, INSERT, UPDATE'),
      ('stripe_events', 'SELECT, INSERT, UPDATE'),
      ('integrations', 'SELECT, INSERT, UPDATE, DELETE'),
      ('monitored_websites', 'SELECT, INSERT, UPDATE, DELETE'),
      ('scheduled_tasks', 'SELECT, INSERT, UPDATE, DELETE'),
      ('notifications', 'SELECT, INSERT, UPDATE, DELETE')
    ) AS grants(table_name, privs)
  LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('GRANT %s ON TABLE %I TO pa_app', privileges, t);
    END IF;
  END LOOP;
END
$$;

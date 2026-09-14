-- Optional: paste as postgres if POST /api/tasks 503s with
-- asyncpg DataError on credit_transactions.created_at
-- (TIMESTAMP WITHOUT TIME ZONE vs aware utc_now).
-- Alembic 0007_credit_timestamptz applies the same conversion.

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.table_name, c.column_name
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name IN (
        'credit_accounts', 'credit_lots', 'credit_transactions',
        'subscriptions', 'stripe_events',
        'assistant_tasks', 'ai_usage', 'assistant_profiles'
      )
      AND c.column_name IN (
        'created_at', 'updated_at', 'completed_at',
        'current_period_start', 'current_period_end', 'expires_at'
      )
      AND c.data_type = 'timestamp without time zone'
  LOOP
    EXECUTE format(
      'ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE %L',
      r.table_name, r.column_name, r.column_name, 'UTC'
    );
  END LOOP;
END
$$;

-- Optional: paste as postgres if GET /api/me/assistant or POST /api/tasks 500s
-- while GET /api/credits and D2 GETs work. Safe to re-run.
-- Alembic 0006_assistant_profile_rls applies the same policies.

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['assistant_profiles', 'assistant_tasks', 'ai_usage']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE NOTICE 'missing table %', t;
      CONTINUE;
    END IF;
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format(
      'CREATE POLICY %I ON %I FOR ALL '
      'USING (user_id::text = current_setting(''app.user_id'', true)) '
      'WITH CHECK (user_id::text = current_setting(''app.user_id'', true))',
      t || '_tenant', t
    );
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE %I TO pa_app', t);
  END LOOP;
END
$$;

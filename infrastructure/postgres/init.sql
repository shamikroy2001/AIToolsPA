-- Runs only on first Postgres volume init.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
    CREATE ROLE pa_app LOGIN PASSWORD 'pa_app';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE personal_assistant TO pa_app;

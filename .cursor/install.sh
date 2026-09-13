#!/usr/bin/env bash
# Idempotent repository bootstrap for the Personal Assistant stack.
# Installs system services (Postgres, Redis), Python/Node dependencies,
# initializes the database, and runs migrations.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Installing system packages (Postgres, Redis) if missing"
if ! command -v pg_ctlcluster >/dev/null 2>&1 || ! command -v redis-server >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    postgresql postgresql-contrib redis-server python3-venv
fi

echo "==> Starting Postgres and Redis for setup"
PG_VERSION="$(ls /usr/lib/postgresql | sort -V | tail -1)"
if ! pg_lsclusters -h 2>/dev/null | grep -q online; then
  sudo pg_ctlcluster "$PG_VERSION" main start || true
fi
if ! redis-cli ping >/dev/null 2>&1; then
  sudo redis-server --daemonize yes
fi

# Wait for Postgres to accept connections.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then break; fi
  sleep 1
done

echo "==> Ensuring database, roles, and passwords"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
ALTER ROLE postgres WITH PASSWORD 'postgres';
SQL
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='personal_assistant'" \
  | grep -q 1 || sudo -u postgres createdb personal_assistant
sudo -u postgres psql -v ON_ERROR_STOP=1 -d personal_assistant <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
    CREATE ROLE pa_app LOGIN PASSWORD 'pa_app';
  END IF;
END
$$;
GRANT CONNECT ON DATABASE personal_assistant TO pa_app;
GRANT ALL ON SCHEMA public TO pa_app;
SQL

echo "==> Writing local env files if absent"
if [ ! -f backend/.env ]; then
  cat > backend/.env <<'ENV'
ENVIRONMENT=staging
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
DATABASE_URL=postgresql+asyncpg://pa_app:pa_app@localhost:5432/personal_assistant
DATABASE_ADMIN_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/personal_assistant
REDIS_URL=redis://localhost:6379/0
PUBLIC_APP_URL=http://localhost:3000
STRIPE_ENABLED=false
CREDENTIAL_ENCRYPTION_KEY=dev-only-local-credential-key-not-for-production
ENV
fi
if [ ! -f frontend/.env.local ]; then
  cat > frontend/.env.local <<'ENV'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_BILLING_ENABLED=false
ENV
fi

echo "==> Installing backend Python dependencies"
cd "$REPO_ROOT/backend"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip -q
pip install -e ".[dev]"

echo "==> Running database migrations"
python -m alembic upgrade head

echo "==> Granting app-role privileges on migrated objects"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d personal_assistant <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pa_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pa_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pa_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO pa_app;
SQL
deactivate

echo "==> Installing frontend Node dependencies"
cd "$REPO_ROOT/frontend"
npm install

echo "==> Install complete"

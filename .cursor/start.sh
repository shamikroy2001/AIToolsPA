#!/usr/bin/env bash
# Per-boot startup: bring up Postgres and Redis. Idempotent and safe to re-run.
set -euo pipefail

echo "==> Starting Postgres"
PG_VERSION="$(ls /usr/lib/postgresql | sort -V | tail -1)"
if ! pg_lsclusters -h 2>/dev/null | grep -q online; then
  sudo pg_ctlcluster "$PG_VERSION" main start
fi

echo "==> Starting Redis"
if ! redis-cli ping >/dev/null 2>&1; then
  sudo redis-server --daemonize yes
fi

# Wait for Postgres readiness before the agent uses it.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then break; fi
  sleep 1
done

echo "==> Postgres and Redis are up"

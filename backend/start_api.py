"""Railway/API entry: bind $PORT immediately so the proxy is not stuck on 502."""

from __future__ import annotations

import logging
import os
import sys
import threading

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("start_api")

MIGRATE_WAIT_SECONDS = 20


def listen_port() -> int:
    raw = (os.environ.get("PORT") or "8000").strip()
    try:
        return int(raw)
    except ValueError:
        log.warning("Invalid PORT=%r; using 8000", raw)
        return 8000


def run_migrations() -> None:
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        log.info("Alembic upgrade head completed")
    except Exception:
        log.exception("Alembic upgrade failed; API already serving /health")


def start_migrations(wait_seconds: float = MIGRATE_WAIT_SECONDS) -> None:
    worker = threading.Thread(target=run_migrations, name="alembic-upgrade", daemon=True)
    worker.start()
    worker.join(timeout=wait_seconds)
    if worker.is_alive():
        log.warning(
            "Alembic still running after %.0fs; binding HTTP so /health can respond",
            wait_seconds,
        )


def main() -> int:
    import uvicorn

    port = listen_port()
    start_migrations(wait_seconds=0)
    log.info("Starting uvicorn on 0.0.0.0:%s", port)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Railway/API entry: bind $PORT immediately so the proxy is not stuck on 502."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from app.core.logging import configure_app_logging

configure_app_logging()
log = logging.getLogger("start_api")

MIGRATE_WAIT_SECONDS = 20
_ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


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

        from app.core.dsn import describe_database_url
        from app.core.settings import get_settings

        settings = get_settings()
        admin_url = settings.database_admin_url or settings.database_url
        log.info("Alembic upgrade head starting (%s)", describe_database_url(admin_url))
        cfg = Config(str(_ALEMBIC_INI))
        command.upgrade(cfg, "head")
        log.info("Alembic upgrade head completed")
    except Exception:
        log.exception("Alembic upgrade failed; API already serving /health")
    finally:
        configure_app_logging()


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
    configure_app_logging()
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

"""Railway/API entry: bind $PORT in-process so the proxy is not stuck on 502."""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("start_api")


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
        log.exception("Alembic upgrade failed; starting API so /health can respond")


def main() -> int:
    run_migrations()
    import uvicorn

    port = listen_port()
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

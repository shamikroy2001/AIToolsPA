"""Process logging. Alembic fileConfig must not be allowed to silence request errors."""

from __future__ import annotations

import logging
import os
import sys

_APP_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "app",
    "app.main",
    "app.assistant",
    "app.errors",
    "app.db",
    "app.ai.gateway",
    "start_api",
)


def configure_app_logging(level: str | None = None) -> None:
    """Ensure stderr logging works after Alembic's fileConfig (which disables loggers)."""
    raw = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    numeric = getattr(logging, raw, logging.INFO)
    root = logging.getLogger()
    root.disabled = False
    root.setLevel(numeric)
    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    for name in _APP_LOGGERS:
        logger = logging.getLogger(name)
        logger.disabled = False
        if logger.level == logging.NOTSET or logger.level > numeric:
            logger.setLevel(numeric)

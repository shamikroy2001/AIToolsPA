"""ASGI entry for hosts that start `uvicorn main:app` instead of `app.main:app`."""

from app.main import app

__all__ = ["app"]

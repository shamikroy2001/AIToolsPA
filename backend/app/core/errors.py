"""JSON 500s with a traceback. Do not let ServerErrorMiddleware emit text/plain."""

from __future__ import annotations

import logging
import sys
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import get_settings

log = logging.getLogger("app.errors")

GENERIC_DETAIL = "Something went wrong. Try again shortly."


def cors_error_headers(request: Request) -> dict[str, str]:
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin and origin in get_settings().cors_origin_list():
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


def json_error_response(request: Request | None = None) -> JSONResponse:
    headers = cors_error_headers(request) if request is not None else {}
    return JSONResponse(
        status_code=500,
        content={"detail": GENERIC_DETAIL},
        headers=headers,
    )


def log_unhandled(method: object, path: object, exc: BaseException) -> None:
    log.exception("Unhandled error on %s %s", method, path)
    print(f"ERROR app.errors Unhandled error on {method} {path}", file=sys.stderr, flush=True)
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


class JsonErrorMiddleware:
    """Catch unhandled exceptions inside CORS so the body is JSON, never text/plain.

    FastAPI attaches ``@app.exception_handler(Exception)`` to ServerErrorMiddleware,
    which sits outside CORS and re-raises after sending. Swallowing here keeps the
    traceback in Railway deploy logs and avoids Starlette's 21-byte plaintext 500.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def inner_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if int(message.get("status") or 0) >= 500:
                    log.error(
                        "HTTP %s on %s %s",
                        message.get("status"),
                        scope.get("method"),
                        scope.get("path"),
                    )
            await send(message)

        try:
            await self.app(scope, receive, inner_send)
        except Exception as exc:
            log_unhandled(scope.get("method"), scope.get("path"), exc)
            if not started:
                await json_error_response(Request(scope))(scope, receive, send)

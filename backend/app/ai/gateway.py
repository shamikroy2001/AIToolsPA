"""Vercel AI Gateway via OpenAI-compatible chat completions. Model IDs stay in env."""

from __future__ import annotations

import logging
import time

import httpx

from app.ai.types import GenerateRequest, GenerateResult
from app.core.settings import Settings

log = logging.getLogger("app.ai.gateway")


def _choice_text(choice: object) -> str:
    if not isinstance(choice, dict):
        return ""
    message = choice.get("message") or {}
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return ""


def _usage_tokens(usage: object, key: str) -> int:
    if not isinstance(usage, dict):
        return 0
    value = usage.get(key)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class GatewayAIProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _model_for(self, route_key: str) -> str:
        mapping = {
            "simple": self._settings.ai_route_simple,
            "default": self._settings.ai_route_default,
            "long_context": self._settings.ai_route_long_context,
        }
        return mapping.get(route_key) or self._settings.ai_route_default or "default"

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        if not self._settings.ai_gateway_api_key or not self._settings.ai_gateway_base_url:
            return GenerateResult(
                text="",
                success=False,
                error="Assistant is not configured",
                provider="gateway",
                model="unconfigured",
            )
        model = self._model_for(request.route_key)
        url = self._settings.ai_gateway_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.ai_gateway_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user_message},
            ],
        }
        started = time.perf_counter()
        last_error = "Assistant unavailable"
        retries = max(1, self._settings.ai_retries)
        for _ in range(retries):
            try:
                async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
                latency = int((time.perf_counter() - started) * 1000)
                if response.status_code >= 400:
                    log.warning("AI gateway HTTP %s", response.status_code)
                    last_error = "Assistant unavailable"
                    continue
                body = response.json()
                if not isinstance(body, dict):
                    last_error = "Assistant unavailable"
                    continue
                choice = (body.get("choices") or [None])[0]
                if not isinstance(choice, dict):
                    last_error = "Assistant unavailable"
                    continue
                text = _choice_text(choice)
                usage = body.get("usage") or {}
                return GenerateResult(
                    text=text,
                    input_tokens=_usage_tokens(usage, "prompt_tokens"),
                    output_tokens=_usage_tokens(usage, "completion_tokens"),
                    latency_ms=latency,
                    success=True,
                    provider="gateway",
                    model=model,
                )
            except Exception:
                log.exception("AI gateway request failed")
                last_error = "Assistant unavailable"
        latency = int((time.perf_counter() - started) * 1000)
        return GenerateResult(
            text="",
            latency_ms=latency,
            success=False,
            error=last_error,
            provider="gateway",
            model=model,
        )

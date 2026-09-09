"""Vercel AI Gateway via OpenAI-compatible chat completions. Model IDs stay in env."""

from __future__ import annotations

import time

import httpx

from app.ai.types import GenerateRequest, GenerateResult
from app.core.settings import Settings


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
                    last_error = "Assistant unavailable"
                    continue
                body = response.json()
                choice = (body.get("choices") or [{}])[0]
                text = ((choice.get("message") or {}).get("content")) or ""
                usage = body.get("usage") or {}
                return GenerateResult(
                    text=text.strip(),
                    input_tokens=int(usage.get("prompt_tokens") or 0),
                    output_tokens=int(usage.get("completion_tokens") or 0),
                    latency_ms=latency,
                    success=True,
                    provider="gateway",
                    model=model,
                )
            except (httpx.HTTPError, ValueError, KeyError):
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

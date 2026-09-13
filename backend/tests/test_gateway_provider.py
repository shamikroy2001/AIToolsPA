"""Gateway adapter must not throw on unexpected provider JSON."""

from __future__ import annotations

import httpx
import pytest

from app.ai.gateway import GatewayAIProvider
from app.ai.types import GenerateRequest
from app.core.settings import Settings


def _settings() -> Settings:
    return Settings(
        ai_gateway_api_key="test-key",
        ai_gateway_base_url="https://gateway.test/v1",
        ai_route_simple="simple-model",
        ai_route_default="default-model",
        ai_retries=1,
        ai_timeout_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_gateway_accepts_list_content(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "choices": [
            {
                "message": {
                    "content": [{"type": "text", "text": "D1 gate ok"}],
                }
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/chat/completions" in str(request.url)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GatewayAIProvider(_settings()).generate(
        GenerateRequest(route_key="simple", system="sys", user_message="hi")
    )
    assert result.success is True
    assert result.text == "D1 gate ok"


@pytest.mark.asyncio
async def test_gateway_unexpected_shape_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"choices": [None]})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GatewayAIProvider(_settings()).generate(
        GenerateRequest(route_key="simple", system="sys", user_message="hi")
    )
    assert result.success is False
    assert result.error == "Assistant unavailable"

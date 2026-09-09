from app.ai.fake import FakeAIProvider
from app.ai.gateway import GatewayAIProvider
from app.ai.provider import AIProvider
from app.core.settings import get_settings

_provider: AIProvider | None = None


def set_ai_provider(provider: AIProvider | None) -> None:
    global _provider
    _provider = provider


def get_ai_provider() -> AIProvider:
    if _provider is not None:
        return _provider
    return GatewayAIProvider(get_settings())

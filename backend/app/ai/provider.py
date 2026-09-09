from typing import Protocol

from app.ai.types import GenerateRequest, GenerateResult


class AIProvider(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...

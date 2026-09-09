from app.ai.types import GenerateRequest, GenerateResult


class FakeAIProvider:
    """Tests only. Never calls a network AI gateway."""

    def __init__(
        self,
        text: str = "Here is a concise answer from your assistant.",
        *,
        succeed: bool = True,
    ) -> None:
        self.text = text
        self.succeed = succeed
        self.calls: list[GenerateRequest] = []

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        self.calls.append(request)
        if not self.succeed:
            return GenerateResult(
                text="",
                success=False,
                error="unavailable",
                provider="fake",
                model="internal-test",
            )
        return GenerateResult(
            text=self.text,
            input_tokens=12,
            output_tokens=18,
            latency_ms=5,
            success=True,
            provider="fake",
            model="internal-test",
        )

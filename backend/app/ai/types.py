from dataclasses import dataclass


@dataclass(frozen=True)
class GenerateRequest:
    route_key: str
    system: str
    user_message: str
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class GenerateResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    success: bool = True
    provider: str = "gateway"
    model: str = "internal"
    error: str | None = None

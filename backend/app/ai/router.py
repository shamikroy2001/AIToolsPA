"""Internal route selection. Opaque keys only — never customer-facing model names."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDecision:
    route_key: str
    complexity: str


class AIRouter:
    def select(
        self,
        *,
        task_type: str,
        user_plan: str,
        message: str,
        complexity: str | None = None,
    ) -> RouteDecision:
        del task_type, user_plan
        text = message or ""
        if complexity:
            key = complexity
        elif len(text) > 8000:
            key = "long_context"
        elif len(text) < 280:
            key = "simple"
        else:
            key = "default"
        if key not in {"simple", "default", "long_context"}:
            key = "default"
        return RouteDecision(route_key=key, complexity=key)

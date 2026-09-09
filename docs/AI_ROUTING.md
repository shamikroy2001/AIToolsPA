# AI routing

Internal only. Customer APIs return task status and assistant text, never provider or model.

```
task_type, plan, complexity, capabilities
        → AIRouter
            → primary config
            → (D2) fallback config
        → Vercel AI Gateway
        → AIUsageService (tokens, provider cost, credits_charged)
```

## D1

- One routing table / config (not user-editable)
- Simple vs default vs long-context internal keys (opaque)
- Happy-path generate; timeout + retry on the same primary
- Record `ai_usage` for later admin (no admin UI in D1)

## D2

- Fallback model on provider failure
- Task-specific routes (email, research, monitor significance)
- Cost controls and richer routing without changing the product UI

Business code must not contain `if provider == "gemini"` (or any vendor). Vendor details stay in the Gateway adapter.

Interfaces (D1):

```python
class AIProvider:
    async def generate(...)
    async def stream(...)

class AIRouter:
    async def select(...)
```

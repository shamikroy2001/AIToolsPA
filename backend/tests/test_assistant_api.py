"""Assistant profile and ask. FakeAIProvider — no live Gateway."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ai import set_ai_provider
from app.ai.fake import FakeAIProvider
from conftest import TOKEN_A, TOKEN_B


def _auth(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _allocate_pro(client: TestClient, user_id: str, event_id: str = "evt_ask") -> None:
    start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
    client.post(
        "/api/webhooks/stripe",
        json={
            "id": event_id,
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": f"sub_{event_id}",
                    "customer": f"cus_{event_id}",
                    "status": "active",
                    "current_period_start": start,
                    "current_period_end": end,
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                    "metadata": {"user_id": user_id},
                }
            },
        },
    )


def _assert_no_ai_leak(payload: object) -> None:
    text = str(payload).lower()
    for forbidden in ("provider", "model", "tokens", "gemini", "openai", "gateway"):
        assert forbidden not in text


def test_ask_does_not_call_get_or_create_profile(
    saas_client: TestClient, monkeypatch
):
    """Live POST /api/tasks 500s because ask() called get_or_create_profile first."""
    from app.services.assistant import AssistantService

    async def trap(self, user_id):
        del self, user_id
        raise AssertionError("ask must not call get_or_create_profile")

    monkeypatch.setattr(AssistantService, "get_or_create_profile", trap)
    me = saas_client.get("/api/me", headers=_auth()).json()
    _allocate_pro(saas_client, me["id"], "evt_no_create")
    response = saas_client.post(
        "/api/tasks",
        json={"message": "Hello"},
        headers=_auth(),
    )
    assert response.status_code == 200
    assert response.json()["credits_charged"] == 5


def test_get_assistant_is_read_only(saas_client: TestClient, monkeypatch):
    """Live GET /api/me/assistant 500s because it INSERTed; GET must not create."""
    from app.services.assistant import AssistantService

    async def trap(self, user_id):
        del self, user_id
        raise AssertionError("GET /api/me/assistant must not call get_or_create_profile")

    monkeypatch.setattr(AssistantService, "get_or_create_profile", trap)
    response = saas_client.get("/api/me/assistant", headers=_auth())
    assert response.status_code == 200
    assert response.json()["assistant_name"] == "Assistant"


def test_patch_assistant_survives_persist_failure(
    saas_client: TestClient, monkeypatch
):
    from app.models.assistant import AssistantProfile
    from app.services.assistant import AssistantService

    original = AssistantService.update_profile

    async def deny_then_update(self, user_id, **kwargs):
        original_add = self._session.add

        def deny(obj) -> None:
            if isinstance(obj, AssistantProfile):
                raise RuntimeError("permission denied for table assistant_profiles")
            original_add(obj)

        self._session.add = deny  # type: ignore[method-assign]
        return await original(self, user_id, **kwargs)

    monkeypatch.setattr(AssistantService, "update_profile", deny_then_update)
    response = saas_client.patch(
        "/api/me/assistant",
        json={"assistant_name": "Riley", "personality": "Calm"},
        headers=_auth(),
    )
    assert response.status_code == 200
    assert response.json()["assistant_name"] == "Riley"
    assert response.json()["personality"] == "Calm"


def test_profile_and_ask_survive_profile_read_failure(
    saas_client: TestClient, monkeypatch
):
    """GET /api/me/assistant and POST /api/tasks must not 500 if profile SELECT fails."""
    from app.services.assistant import AssistantService

    async def boom(self, user_id):
        del self, user_id
        raise RuntimeError("rls or schema mismatch on assistant_profiles")

    monkeypatch.setattr(AssistantService, "get_profile", boom)
    profile = saas_client.get("/api/me/assistant", headers=_auth())
    assert profile.status_code == 200
    assert profile.json()["assistant_name"] == "Assistant"
    me = saas_client.get("/api/me", headers=_auth()).json()
    _allocate_pro(saas_client, me["id"], "evt_profile_read")
    asked = saas_client.post(
        "/api/tasks",
        json={"message": "Hello"},
        headers=_auth(),
    )
    assert asked.status_code == 200
    assert asked.json()["credits_charged"] == 5
    _assert_no_ai_leak(asked.json())


def test_profile_defaults_and_update(saas_client: TestClient):
    created = saas_client.get("/api/me/assistant", headers=_auth())
    assert created.status_code == 200
    body = created.json()
    assert body["assistant_name"] == "Assistant"
    assert "model" not in body
    patched = saas_client.patch(
        "/api/me/assistant",
        json={"assistant_name": "Riley", "personality": "Calm", "response_style": "brief"},
        headers=_auth(),
    )
    assert patched.status_code == 200
    assert patched.json()["assistant_name"] == "Riley"
    leaked = saas_client.patch(
        "/api/me/assistant",
        json={"model": "anything"},
        headers=_auth(),
    )
    assert leaked.status_code == 422


def test_ask_without_credits_is_402_and_does_not_call_ai(saas_client: TestClient):
    provider = FakeAIProvider()
    set_ai_provider(provider)
    saas_client.get("/api/me", headers=_auth())
    response = saas_client.post("/api/tasks", json={"message": "Hello"}, headers=_auth())
    assert response.status_code == 402
    assert "Upgrade" in response.json()["detail"]
    assert provider.calls == []
    credits = saas_client.get("/api/credits", headers=_auth()).json()
    assert credits["available"] == 0


def test_ask_charges_credits_and_hides_routing(saas_client: TestClient):
    me = saas_client.get("/api/me", headers=_auth()).json()
    _allocate_pro(saas_client, me["id"])
    before = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    response = saas_client.post(
        "/api/tasks",
        json={"message": "Summarize my week."},
        headers=_auth(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["task_type"] == "assistant_ask"
    assert body["reply"] == "Here is a concise answer from your assistant."
    assert body["credits_charged"] == 5
    _assert_no_ai_leak(body)
    after = saas_client.get("/api/credits", headers=_auth()).json()
    assert after["available"] == before - 5
    listed = saas_client.get("/api/tasks", headers=_auth()).json()
    assert listed[0]["id"] == body["id"]
    one = saas_client.get(f"/api/tasks/{body['id']}", headers=_auth())
    assert one.status_code == 200
    assert one.json()["message"] == "Summarize my week."


def test_user_cannot_read_other_tasks(saas_client: TestClient):
    me_a = saas_client.get("/api/me", headers=_auth(TOKEN_A)).json()
    saas_client.get("/api/me", headers=_auth(TOKEN_B))
    _allocate_pro(saas_client, me_a["id"], "evt_iso")
    created = saas_client.post(
        "/api/tasks",
        json={"message": "Private note"},
        headers=_auth(TOKEN_A),
    ).json()
    denied = saas_client.get(f"/api/tasks/{created['id']}", headers=_auth(TOKEN_B))
    assert denied.status_code == 404
    listed_b = saas_client.get("/api/tasks", headers=_auth(TOKEN_B)).json()
    assert listed_b == []


def test_ai_failure_releases_reservation(saas_client: TestClient):
    set_ai_provider(FakeAIProvider(succeed=False))
    me = saas_client.get("/api/me", headers=_auth()).json()
    _allocate_pro(saas_client, me["id"], "evt_fail_ai")
    before = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    response = saas_client.post("/api/tasks", json={"message": "Hello"}, headers=_auth())
    assert response.status_code == 503
    after = saas_client.get("/api/credits", headers=_auth()).json()["available"]
    assert after == before
    set_ai_provider(FakeAIProvider())

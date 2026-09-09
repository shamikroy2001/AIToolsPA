"""D1a auth and tenant isolation. Uses StaticTokenVerifier — no live Clerk or JWKS."""

from fastapi.testclient import TestClient

from conftest import TOKEN_A, TOKEN_B


def test_health_is_public(saas_client: TestClient):
    response = saas_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_me_rejects_missing_token(saas_client: TestClient):
    response = saas_client.get("/api/me")
    assert response.status_code == 401


def test_me_rejects_invalid_token(saas_client: TestClient):
    response = saas_client.get(
        "/api/me", headers={"Authorization": "Bearer unknown"}
    )
    assert response.status_code == 401


def test_me_creates_user(saas_client: TestClient):
    response = saas_client.get(
        "/api/me", headers={"Authorization": f"Bearer {TOKEN_A}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "a@example.com"
    assert body["plan"] == "none"
    assert body["status"] == "active"
    assert "id" in body
    assert "clerk_user_id" not in body


def test_user_cannot_read_another_user(saas_client: TestClient):
    first = saas_client.get(
        "/api/me", headers={"Authorization": f"Bearer {TOKEN_A}"}
    )
    second = saas_client.get(
        "/api/me", headers={"Authorization": f"Bearer {TOKEN_B}"}
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["email"] == "a@example.com"
    assert second.json()["email"] == "b@example.com"


def test_me_is_stable_for_same_token(saas_client: TestClient):
    first = saas_client.get(
        "/api/me", headers={"Authorization": f"Bearer {TOKEN_A}"}
    )
    second = saas_client.get(
        "/api/me", headers={"Authorization": f"Bearer {TOKEN_A}"}
    )
    assert first.json()["id"] == second.json()["id"]

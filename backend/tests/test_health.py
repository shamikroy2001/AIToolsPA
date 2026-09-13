from fastapi.testclient import TestClient

from app.main import app
from main import app as shim_app

client = TestClient(app)


def test_asgi_shim_exports_the_same_app():
    assert shim_app is app


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "personal-assistant-api"
    assert body["release"] == "D1-staging"
    assert body["supabase"] in {"ok", "unconfigured", "error"}


def test_api_health_alias():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

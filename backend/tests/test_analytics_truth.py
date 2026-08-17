import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import _auth_requests, _requests, app


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
    }
    settings.app_env = "test"
    settings.database_path = tmp_path / "analytics-truth.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = False
    _requests.clear()
    _auth_requests.clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        _requests.clear()
        _auth_requests.clear()
        for key, value in original.items():
            setattr(settings, key, value)


def test_new_account_analytics_contains_no_manufactured_activity(client: TestClient):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Fresh Creator", "email": "fresh-analytics@example.com", "password": "Secure123"},
    )
    assert signup.status_code == 201

    response = client.get("/api/v1/analytics")
    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["projects"] == 0
    assert payload["summary"]["clips"] == 0
    assert payload["summary"]["avg_score"] == 0
    assert payload["summary"]["exports"] == 0
    assert payload["summary"]["minutes_processed"] == 0
    assert payload["categories"] == []
    assert payload["activity"] == []


def test_analytics_requires_authentication(client: TestClient):
    response = client.get("/api/v1/analytics")
    assert response.status_code == 401

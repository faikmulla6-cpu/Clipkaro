import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.settings import AccountSettingsPatch, update_account_settings
from app.core.config import get_settings
from app.core.database import execute, fetch_one
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
    settings.database_path = tmp_path / "settings-test.db"
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


def _signup(client: TestClient, email: str = "settings@example.com") -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={"name": "Settings Creator", "email": email, "password": "Secure123"},
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    return response.json()["user"]


def test_legacy_or_new_account_gets_safe_defaults_without_preference_row(client: TestClient):
    user = _signup(client)
    before = asyncio.run(fetch_one("SELECT * FROM user_preferences WHERE user_id=?", (user["id"],)))
    assert before is None

    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    assert response.json() == {
        "name": "Settings Creator",
        "email": "settings@example.com",
        "default_language": "auto",
        "timezone": "Asia/Kolkata",
        "creator_category": "auto",
    }


def test_all_editable_settings_persist_across_refresh_and_login(client: TestClient):
    _signup(client)
    payload = {
        "name": "Faik Creator",
        "default_language": "hinglish",
        "timezone": "Asia/Dubai",
        "creator_category": "podcast",
    }
    saved = client.patch("/api/v1/settings", json=payload)
    assert saved.status_code == 200
    assert saved.json() == {**payload, "email": "settings@example.com"}

    refreshed = client.get("/api/v1/settings")
    assert refreshed.status_code == 200
    assert refreshed.json() == saved.json()

    # This lifecycle assertion cares that logout really clears the session,
    # rather than depending on FastAPI's injected Response status wrapper.
    client.post("/api/v1/auth/logout")
    assert client.cookies.get("access_token") is None
    assert client.cookies.get("csrf_token") is None
    client.headers.pop("X-CSRF-Token", None)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "settings@example.com", "password": "Secure123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["name"] == "Faik Creator"
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    after_login = client.get("/api/v1/settings")
    assert after_login.status_code == 200
    assert after_login.json() == saved.json()


def test_partial_update_preserves_existing_preferences(client: TestClient):
    _signup(client)
    initial = client.patch("/api/v1/settings", json={
        "default_language": "mr",
        "timezone": "Europe/London",
        "creator_category": "education",
    })
    assert initial.status_code == 200

    rename = client.patch("/api/v1/settings", json={"name": "Renamed Creator"})
    assert rename.status_code == 200
    assert rename.json()["name"] == "Renamed Creator"
    assert rename.json()["default_language"] == "mr"
    assert rename.json()["timezone"] == "Europe/London"
    assert rename.json()["creator_category"] == "education"


def test_invalid_setting_is_rejected_before_any_field_changes(client: TestClient):
    _signup(client)
    before = client.get("/api/v1/settings").json()

    invalid_cases = [
        {"name": "Should Not Save", "default_language": "klingon"},
        {"name": "Should Not Save", "timezone": "Mars/Olympus"},
        {"name": "Should Not Save", "creator_category": "unsupported-category"},
        {"name": "Should Not Save", "unknown_setting": True},
    ]
    for body in invalid_cases:
        response = client.patch("/api/v1/settings", json=body)
        assert response.status_code == 422
        assert client.get("/api/v1/settings").json() == before


def test_preferences_are_isolated_between_users(client: TestClient):
    first = _signup(client, "first-settings@example.com")
    saved = client.patch("/api/v1/settings", json={
        "default_language": "hi",
        "timezone": "Asia/Kolkata",
        "creator_category": "business",
    })
    assert saved.status_code == 200
    client.post("/api/v1/auth/logout")

    second = _signup(client, "second-settings@example.com")
    second_defaults = client.get("/api/v1/settings")
    assert second_defaults.status_code == 200
    assert second_defaults.json()["default_language"] == "auto"
    assert second_defaults.json()["creator_category"] == "auto"

    first_row = asyncio.run(fetch_one("SELECT * FROM user_preferences WHERE user_id=?", (first["id"],)))
    second_row = asyncio.run(fetch_one("SELECT * FROM user_preferences WHERE user_id=?", (second["id"],)))
    assert first_row and first_row["creator_category"] == "business"
    assert second_row is None


def test_concurrent_partial_saves_do_not_lose_each_others_fields(client: TestClient):
    user = _signup(client)
    db_user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)))
    assert db_user

    async def save_concurrently():
        await asyncio.gather(
            update_account_settings(AccountSettingsPatch(default_language="hi"), db_user),
            update_account_settings(AccountSettingsPatch(creator_category="business"), db_user),
        )

    asyncio.run(save_concurrently())
    final = client.get("/api/v1/settings")
    assert final.status_code == 200
    assert final.json()["default_language"] == "hi"
    assert final.json()["creator_category"] == "business"


def test_preference_row_cascades_when_account_is_deleted(client: TestClient):
    user = _signup(client)
    saved = client.patch("/api/v1/settings", json={"default_language": "en"})
    assert saved.status_code == 200
    row = asyncio.run(fetch_one("SELECT * FROM user_preferences WHERE user_id=?", (user["id"],)))
    assert row and row["default_language"] == "en"

    asyncio.run(execute("DELETE FROM users WHERE id=?", (user["id"],)))
    deleted = asyncio.run(fetch_one("SELECT * FROM user_preferences WHERE user_id=?", (user["id"],)))
    assert deleted is None

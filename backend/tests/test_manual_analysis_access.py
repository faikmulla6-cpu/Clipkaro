from unittest.mock import AsyncMock, patch
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import fetch_all, fetch_one
from app.main import app, _auth_requests, _requests


SEGMENTS = [
    {"start": 0, "end": 12, "text": "Most creators lose attention before the useful part begins."},
    {"start": 12, "end": 27, "text": "Make the result clear before you explain the process."},
    {"start": 27, "end": 44, "text": "That gives the viewer a reason to stay until the end."},
]


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "allow_manual_analysis_in_development": settings.allow_manual_analysis_in_development,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
    }
    settings.app_env = "test"
    settings.allow_manual_analysis_in_development = False
    settings.database_path = tmp_path / "manual-analysis-test.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = True
    # Rate-limit buckets are process-global by design in the application. Clear
    # them between isolated TestClient lifespans so security tests do not consume
    # one another's authentication allowance.
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


def _set_csrf(client: TestClient) -> None:
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")


def _signup_creator(client: TestClient, name: str, email: str) -> None:
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": name, "email": email, "password": "Secure123"},
    )
    assert signup.status_code == 201
    assert signup.json()["user"]["role"] == "creator"
    _set_csrf(client)


def _upload_without_processing(client: TestClient, title: str = "Manual analysis security") -> dict:
    with patch("app.api.routes._process_project", new=AsyncMock()):
        response = client.post(
            "/api/v1/projects/upload",
            data={"title": title},
            files={"file": ("manual.mp4", b"manual-analysis-test", "video/mp4")},
        )
    assert response.status_code == 201
    return response.json()


def test_production_creator_cannot_call_manual_analysis_with_or_without_segments(client: TestClient):
    _signup_creator(client, "Production Creator", "prod-creator@example.com")
    upload = _upload_without_processing(client)

    settings = get_settings()
    settings.app_env = "production"
    settings.allow_manual_analysis_in_development = True  # must never override production denial

    supplied = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en", "segments": SEGMENTS},
    )
    assert supplied.status_code == 403
    assert "restricted" in supplied.json()["detail"].lower()

    direct_transcription = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en"},
    )
    assert direct_transcription.status_code == 403

    transcripts = asyncio.run(fetch_all("SELECT * FROM transcripts WHERE video_id=?", (upload["video_id"],)))
    clips = asyncio.run(fetch_all("SELECT * FROM clips WHERE video_id=?", (upload["video_id"],)))
    project = asyncio.run(fetch_one("SELECT status FROM projects WHERE id=?", (upload["id"],)))
    assert transcripts == []
    assert clips == []
    assert project and project["status"] != "ready"


def test_production_admin_can_use_manual_analysis_for_internal_recovery(client: TestClient):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@clipkaro.ai", "password": "ClipKaro123!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"
    _set_csrf(client)
    upload = _upload_without_processing(client, "Admin recovery")

    settings = get_settings()
    settings.app_env = "production"
    settings.allow_manual_analysis_in_development = False
    response = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en", "segments": SEGMENTS},
    )
    assert response.status_code == 200
    assert response.json()
    transcript = asyncio.run(fetch_one("SELECT id FROM transcripts WHERE video_id=?", (upload["video_id"],)))
    assert transcript


def test_test_environment_creator_can_use_manual_analysis_for_automated_qa(client: TestClient):
    _signup_creator(client, "QA Creator", "qa-creator@example.com")
    upload = _upload_without_processing(client, "QA analysis")

    settings = get_settings()
    assert settings.app_env == "test"
    settings.allow_manual_analysis_in_development = False
    response = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en", "segments": SEGMENTS},
    )
    assert response.status_code == 200
    assert response.json()


def test_development_creator_requires_explicit_internal_opt_in(client: TestClient):
    _signup_creator(client, "Dev Creator", "dev-creator@example.com")
    upload = _upload_without_processing(client, "Developer QA")

    settings = get_settings()
    settings.app_env = "development"
    settings.allow_manual_analysis_in_development = False
    blocked = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en", "segments": SEGMENTS},
    )
    assert blocked.status_code == 403

    settings.allow_manual_analysis_in_development = True
    allowed = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en", "segments": SEGMENTS},
    )
    assert allowed.status_code == 200
    assert allowed.json()


def test_unknown_environment_fails_closed_for_creator(client: TestClient):
    _signup_creator(client, "Preview Creator", "preview-creator@example.com")
    upload = _upload_without_processing(client, "Preview environment")

    settings = get_settings()
    settings.app_env = "preview"
    settings.allow_manual_analysis_in_development = True
    response = client.post(
        f"/api/v1/projects/{upload['id']}/analyse",
        json={"language": "en", "segments": SEGMENTS},
    )
    assert response.status_code == 403

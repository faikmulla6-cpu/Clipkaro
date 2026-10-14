import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.main import _auth_requests, _requests, app
from app.services.auth import create_token
from app.services.upload_scanner import (
    UploadMalwareDetected,
    UploadScannerUnavailable,
    _local_scan_timeout_seconds,
    scan_upload,
)


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
        "app_env": settings.app_env,
        "email_verification_required": settings.email_verification_required,
        "upload_scan_required": settings.upload_scan_required,
        "clamav_host": settings.clamav_host,
        "password_reset_resend_cooldown_seconds": settings.password_reset_resend_cooldown_seconds,
        "password_reset_max_sends_per_hour": settings.password_reset_max_sends_per_hour,
    }
    settings.database_path = tmp_path / "security-foundation.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "security-foundation-test-secret-with-32-chars"
    settings.seed_demo_user = False
    settings.app_env = "test"
    settings.email_verification_required = False
    settings.upload_scan_required = False
    settings.clamav_host = ""
    settings.password_reset_resend_cooldown_seconds = 60
    settings.password_reset_max_sends_per_hour = 5
    _requests.clear()
    _auth_requests.clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
        _requests.clear()
        _auth_requests.clear()


def _signup(client: TestClient, email: str = "security@example.com", password: str = "Secure123"):
    return client.post(
        "/api/v1/auth/signup",
        json={"name": "Security Creator", "email": email, "password": password},
    )


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def test_logout_revokes_copied_server_side_session(client: TestClient):
    signup = _signup(client)
    assert signup.status_code == 201, signup.text
    stolen_token = client.cookies.get("access_token")
    assert stolen_token

    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email='security@example.com'"))
    assert user
    sessions = asyncio.run(fetch_all("SELECT * FROM auth_sessions WHERE user_id=?", (user["id"],)))
    assert len(sessions) == 1
    assert sessions[0]["revoked_at"] is None

    response = client.post("/api/v1/auth/logout", headers=_csrf(client))
    assert response.status_code == 204
    stored = asyncio.run(fetch_one("SELECT revoked_at FROM auth_sessions WHERE id=?", (sessions[0]["id"],)))
    assert stored and stored["revoked_at"]

    replay = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {stolen_token}"})
    assert replay.status_code == 401
    assert "signed out" in replay.json()["detail"].lower()


def test_logout_all_invalidates_every_device_session(client: TestClient):
    assert _signup(client, "devices@example.com").status_code == 201
    first_token = client.cookies.get("access_token")
    assert first_token

    second = client.post(
        "/api/v1/auth/login",
        json={"email": "devices@example.com", "password": "Secure123"},
    )
    assert second.status_code == 200
    second_token = client.cookies.get("access_token")
    assert second_token and second_token != first_token

    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email='devices@example.com'"))
    sessions = asyncio.run(fetch_all("SELECT * FROM auth_sessions WHERE user_id=?", (user["id"],)))
    assert len(sessions) == 2

    revoked = client.post("/api/v1/auth/logout-all", headers=_csrf(client))
    assert revoked.status_code == 204
    fresh_user = asyncio.run(fetch_one("SELECT session_version FROM users WHERE id=?", (user["id"],)))
    assert int(fresh_user["session_version"]) == 1

    for token in (first_token, second_token):
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_password_reset_is_hashed_enumeration_safe_one_time_and_revokes_sessions(client: TestClient, monkeypatch):
    old_password = "Secure123"
    new_password = "Changed456"
    assert _signup(client, "reset@example.com", old_password).status_code == 201
    old_session = client.cookies.get("access_token")
    assert old_session
    captured: list[str] = []

    async def fake_send(_recipient: str, _name: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("app.api.account_security.send_password_reset_email", fake_send)
    known = client.post("/api/v1/auth/password/forgot", json={"email": "reset@example.com"})
    unknown = client.post("/api/v1/auth/password/forgot", json={"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(captured) == 1

    raw_token = captured[0]
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email='reset@example.com'"))
    challenge = asyncio.run(fetch_one("SELECT * FROM password_resets WHERE user_id=?", (user["id"],)))
    assert challenge
    assert challenge["token_hash"] == hashlib.sha256(raw_token.encode()).hexdigest()
    assert challenge["token_hash"] != raw_token

    reset = client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "password": new_password},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["reset"] is True

    replay_session = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_session}"})
    assert replay_session.status_code == 401
    replay_link = client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "password": "Again789"},
    )
    assert replay_link.status_code == 400

    old_login = client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": old_password})
    assert old_login.status_code == 401
    new_login = client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": new_password})
    assert new_login.status_code == 200


def test_expired_password_reset_link_is_rejected(client: TestClient, monkeypatch):
    assert _signup(client, "expired-reset@example.com").status_code == 201
    captured: list[str] = []

    async def fake_send(_recipient: str, _name: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("app.api.account_security.send_password_reset_email", fake_send)
    assert client.post("/api/v1/auth/password/forgot", json={"email": "expired-reset@example.com"}).status_code == 202
    user = asyncio.run(fetch_one("SELECT id FROM users WHERE email='expired-reset@example.com'"))
    asyncio.run(execute(
        "UPDATE password_resets SET expires_at=? WHERE user_id=?",
        ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), user["id"]),
    ))
    expired = client.post(
        "/api/v1/auth/password/reset",
        json={"token": captured[0], "password": "Changed456"},
    )
    assert expired.status_code == 410


def test_legacy_stateless_jwt_is_rejected_outside_tests(client: TestClient):
    assert _signup(client, "legacy-session@example.com").status_code == 201
    user = asyncio.run(fetch_one("SELECT id FROM users WHERE email='legacy-session@example.com'"))
    legacy = create_token(user["id"])
    settings = get_settings()
    previous = settings.app_env
    settings.app_env = "development"
    try:
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"})
    finally:
        settings.app_env = previous
    assert response.status_code == 401
    assert "retired" in response.json()["detail"].lower()


def test_local_clamscan_timeout_scales_with_bounded_upload_size(tmp_path):
    settings = get_settings()
    original_timeout = settings.clamav_timeout_seconds
    path = tmp_path / "large.mp4"
    with path.open("wb") as handle:
        handle.truncate(54 * 1024 * 1024)
    try:
        settings.clamav_timeout_seconds = 30
        assert _local_scan_timeout_seconds(path) >= 138
        with path.open("wb") as handle:
            handle.truncate(500 * 1024 * 1024)
        assert _local_scan_timeout_seconds(path) == 600
        settings.clamav_timeout_seconds = 900
        assert _local_scan_timeout_seconds(path) == 900
    finally:
        settings.clamav_timeout_seconds = original_timeout


def test_required_scanner_fails_closed_when_unconfigured(tmp_path):
    settings = get_settings()
    original_required, original_host = settings.upload_scan_required, settings.clamav_host
    settings.upload_scan_required = True
    settings.clamav_host = ""
    path = tmp_path / "clean-looking.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"0" * 64)
    try:
        with pytest.raises(UploadScannerUnavailable):
            asyncio.run(scan_upload(path))
    finally:
        settings.upload_scan_required = original_required
        settings.clamav_host = original_host


def test_malware_rejection_happens_before_project_or_job_creation(client: TestClient, monkeypatch):
    assert _signup(client, "scan@example.com").status_code == 201

    async def reject(_path):
        raise UploadMalwareDetected("Eicar-Test-Signature")

    monkeypatch.setattr("app.api.secure_upload.scan_upload", reject)
    response = client.post(
        "/api/v1/projects/upload",
        headers=_csrf(client),
        files={"file": ("infected.mp4", b"not-really-video", "video/mp4")},
        data={"title": "Bad upload"},
    )
    assert response.status_code == 422
    assert asyncio.run(fetch_all("SELECT id FROM projects")) == []
    assert asyncio.run(fetch_all("SELECT id FROM jobs")) == []
    upload_dir = get_settings().upload_dir
    assert not list(upload_dir.glob("*"))

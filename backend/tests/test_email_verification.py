import asyncio
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_one
from app.main import _auth_requests, _requests, app
from app.services.email_verification import init_email_verification
from app.services.transactional_email import TransactionalEmail, send_transactional_email


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
        "email_verification_resend_cooldown_seconds": settings.email_verification_resend_cooldown_seconds,
        "email_verification_max_sends_per_hour": settings.email_verification_max_sends_per_hour,
        "smtp_host": settings.smtp_host,
        "smtp_username": settings.smtp_username,
        "smtp_password": settings.smtp_password,
        "smtp_from_email": settings.smtp_from_email,
        "resend_api_key": settings.resend_api_key,
        "email_from": settings.email_from,
        "app_public_url": settings.app_public_url,
    }
    settings.database_path = tmp_path / "email-verification.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "email-verification-test-secret"
    settings.seed_demo_user = False
    settings.app_env = "test"
    settings.email_verification_required = True
    settings.email_verification_resend_cooldown_seconds = 60
    settings.email_verification_max_sends_per_hour = 5
    settings.smtp_host = ""
    settings.smtp_username = ""
    settings.smtp_password = ""
    settings.smtp_from_email = ""
    settings.resend_api_key = ""
    settings.email_from = ""
    settings.app_public_url = "http://testserver"
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


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def _signup(client: TestClient, email: str = "creator@example.com"):
    return client.post(
        "/api/v1/auth/signup",
        json={"name": "Creator", "email": email, "password": "Secure123"},
    )


def test_signup_token_is_hashed_compute_is_blocked_then_verification_unlocks(client: TestClient, monkeypatch):
    captured: list[str] = []

    async def fake_send(_recipient: str, _name: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("app.api.email_verification.send_verification_email", fake_send)
    # Switch enforcement on after lifespan startup so this integration test
    # exercises production behavior without production startup requirements.
    get_settings().app_env = "development"

    signup = _signup(client)
    assert signup.status_code == 201, signup.text
    assert signup.json()["verification"]["verified"] is False
    assert signup.json()["verification"]["can_process"] is False
    assert signup.json()["verification_email_sent"] is True
    assert len(captured) == 1

    raw_token = captured[0]
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email=?", ("creator@example.com",)))
    assert user and user["email_verified_at"] is None
    challenge = asyncio.run(fetch_one("SELECT * FROM email_verifications WHERE user_id=?", (user["id"],)))
    assert challenge
    assert challenge["token_hash"] == hashlib.sha256(raw_token.encode()).hexdigest()
    assert challenge["token_hash"] != raw_token

    # The middleware runs before multipart parsing, so even a malformed direct
    # upload call is rejected for verification before it can touch storage/AI.
    blocked = client.post("/api/v1/projects/upload", headers=_csrf(client))
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "EMAIL_VERIFICATION_REQUIRED"
    for path in ("/cartoon-studio/projects", "/cartoon-studio/projects/fixture/retry"):
        cartoon = client.post("/api/v1" + path, headers=_csrf(client))
        assert cartoon.status_code == 403
        assert cartoon.json()["code"] == "EMAIL_VERIFICATION_REQUIRED"

    verified = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True

    # Same successful link is replay-safe/idempotent rather than mutating twice.
    replay = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert replay.status_code == 200

    status = client.get("/api/v1/auth/verification-status")
    assert status.status_code == 200
    assert status.json()["verified"] is True
    assert status.json()["can_process"] is True

    # Now the request reaches normal FastAPI body validation (422: missing file),
    # proving the verification middleware is no longer the blocker.
    allowed = client.post("/api/v1/projects/upload", headers=_csrf(client))
    assert allowed.status_code == 422


def test_resend_replaces_previous_token_and_rate_limit_is_durable(client: TestClient, monkeypatch):
    captured: list[str] = []

    async def fake_send(_recipient: str, _name: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("app.api.email_verification.send_verification_email", fake_send)
    get_settings().app_env = "development"
    signup = _signup(client, "resend@example.com")
    assert signup.status_code == 201
    original_token = captured[-1]
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email=?", ("resend@example.com",)))
    assert user

    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    asyncio.run(execute(
        "UPDATE email_verifications SET last_sent_at=?,send_window_started_at=?,send_count=1 WHERE user_id=?",
        (old, old, user["id"]),
    ))
    resend = client.post("/api/v1/auth/resend-verification", headers=_csrf(client), json={})
    assert resend.status_code == 200, resend.text
    assert resend.json()["sent"] is True
    replacement_token = captured[-1]
    assert replacement_token != original_token

    old_link = client.post("/api/v1/auth/verify-email", json={"token": original_token})
    assert old_link.status_code == 400

    # Persisted timestamp throttles an immediate second resend even if route
    # code is invoked again; this is not an in-memory-only limiter.
    throttled = client.post("/api/v1/auth/resend-verification", headers=_csrf(client), json={})
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) >= 1

    replacement = client.post("/api/v1/auth/verify-email", json={"token": replacement_token})
    assert replacement.status_code == 200


def test_expired_verification_token_cannot_unlock_account(client: TestClient, monkeypatch):
    captured: list[str] = []

    async def fake_send(_recipient: str, _name: str, token: str) -> None:
        captured.append(token)

    monkeypatch.setattr("app.api.email_verification.send_verification_email", fake_send)
    get_settings().app_env = "development"
    assert _signup(client, "expired@example.com").status_code == 201
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email=?", ("expired@example.com",)))
    assert user
    asyncio.run(execute(
        "UPDATE email_verifications SET expires_at=? WHERE user_id=?",
        ("2000-01-01T00:00:00+00:00", user["id"]),
    ))

    expired = client.post("/api/v1/auth/verify-email", json={"token": captured[-1]})
    assert expired.status_code == 410
    stored = asyncio.run(fetch_one("SELECT email_verified_at FROM users WHERE id=?", (user["id"],)))
    assert stored and stored["email_verified_at"] is None


def test_production_like_signup_fails_closed_when_resend_is_missing(client: TestClient):
    settings = get_settings()
    settings.app_env = "staging"
    settings.smtp_host = ""
    settings.smtp_from_email = ""

    response = _signup(client, "stranded@example.com")
    assert response.status_code == 503
    assert asyncio.run(fetch_one("SELECT id FROM users WHERE email=?", ("stranded@example.com",))) is None


def test_resend_delivery_uses_server_only_bearer_auth_and_html_text(monkeypatch):
    settings = get_settings()
    original_key, original_from = settings.resend_api_key, settings.email_from
    settings.resend_api_key = "re_test_only"
    settings.email_from = "ClipKaro AI <verify@example.test>"
    captured = {}

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr("app.services.transactional_email.urllib.request.urlopen", fake_urlopen)
    try:
        asyncio.run(send_transactional_email(TransactionalEmail(
            to="creator@example.test", subject="Verify", html="<p>Verify</p>", text="Verify",
        )))
    finally:
        settings.resend_api_key, settings.email_from = original_key, original_from

    assert captured["headers"]["Authorization"] == "Bearer re_test_only"
    assert captured["headers"]["User-agent"] == "ClipKaro-TransactionalEmail/1.0"
    assert '"html": "<p>Verify</p>"' in captured["body"]
    assert '"text": "Verify"' in captured["body"]


def test_existing_accounts_are_verified_only_by_one_time_column_migration(tmp_path):
    settings = get_settings()
    original_path = settings.database_path
    settings.database_path = tmp_path / "legacy.db"
    try:
        conn = sqlite3.connect(settings.database_path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """CREATE TABLE users (
                 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
                 password_hash TEXT NOT NULL, plan TEXT NOT NULL DEFAULT 'free', role TEXT NOT NULL DEFAULT 'creator',
                 onboarding_complete INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                 billing_reference TEXT, plan_started_at TEXT, plan_expires_at TEXT,
                 cancel_at_period_end INTEGER NOT NULL DEFAULT 0
               )"""
        )
        conn.execute(
            "INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "legacy-user", "Legacy", "legacy@example.com", "hash", "free", "creator", 1,
                "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
        conn.close()

        asyncio.run(init_email_verification())
        migrated = asyncio.run(fetch_one("SELECT email_verified_at FROM users WHERE id='legacy-user'"))
        assert migrated and migrated["email_verified_at"] == "2026-01-01T00:00:00+00:00"

        # A user inserted after the column exists is not silently auto-verified
        # by a later startup/migration call.
        conn = sqlite3.connect(settings.database_path)
        conn.execute(
            """INSERT INTO users(
                 id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at,email_verified_at
               ) VALUES (?,?,?,?,?,?,?,?,?,NULL)""",
            (
                "new-user", "New", "new@example.com", "hash", "free", "creator", 0,
                "2026-08-08T00:00:00+00:00", "2026-08-08T00:00:00+00:00",
            ),
        )
        conn.commit()
        conn.close()
        asyncio.run(init_email_verification())
        fresh = asyncio.run(fetch_one("SELECT email_verified_at FROM users WHERE id='new-user'"))
        assert fresh and fresh["email_verified_at"] is None
    finally:
        settings.database_path = original_path

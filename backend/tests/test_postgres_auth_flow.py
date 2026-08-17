from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import _auth_requests, _requests, app


pytestmark = pytest.mark.skipif(
    get_settings().normalized_database_backend != "postgres",
    reason="PostgreSQL auth integration requires DATABASE_BACKEND=postgres",
)


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token, "Expected CSRF cookie after authenticated signup/login"
    return {"X-CSRF-Token": token}


def test_postgres_signup_login_resend_and_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    original_cooldown = settings.email_verification_resend_cooldown_seconds
    captured_tokens: list[str] = []

    async def fake_send(_recipient: str, _name: str, token: str) -> str:
        captured_tokens.append(token)
        return "https://clipkaro.pro/verify-email#token=redacted"

    monkeypatch.setattr("app.api.email_verification.send_verification_email", fake_send)
    settings.email_verification_resend_cooldown_seconds = 1
    _requests.clear()
    _auth_requests.clear()

    email = "postgres-auth-ci@clipkaro.example"
    password = "Secure123"

    try:
        with TestClient(app) as client:
            signup = client.post(
                "/api/v1/auth/signup",
                json={"name": "Postgres Creator", "email": email, "password": password},
            )
            assert signup.status_code == 201, signup.text
            assert signup.json()["verification_email_sent"] is True
            assert signup.json()["verification"]["verified"] is False
            assert signup.json()["verification"]["can_process"] is False
            assert len(captured_tokens) == 1
            first_token = captured_tokens[-1]
            assert client.cookies.get("access_token")
            assert client.cookies.get("csrf_token")

            status = client.get("/api/v1/auth/verification-status")
            assert status.status_code == 200, status.text
            assert status.json()["verified"] is False

            logout = client.post("/api/v1/auth/logout", headers=_csrf(client))
            assert logout.status_code == 204, logout.text

            login = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["email"] == email
            assert client.cookies.get("access_token")
            assert client.cookies.get("csrf_token")

            # Resend has a durable per-account cooldown. Shorten it only for this
            # isolated CI account, then prove the new token replaces the old one.
            time.sleep(1.1)
            resend = client.post(
                "/api/v1/auth/resend-verification",
                headers=_csrf(client),
                json={},
            )
            assert resend.status_code == 200, resend.text
            assert resend.json()["sent"] is True
            assert len(captured_tokens) == 2
            second_token = captured_tokens[-1]
            assert second_token != first_token

            replaced = client.post("/api/v1/auth/verify-email", json={"token": first_token})
            assert replaced.status_code == 400, replaced.text

            verified = client.post("/api/v1/auth/verify-email", json={"token": second_token})
            assert verified.status_code == 200, verified.text
            assert verified.json()["verified"] is True

            final_status = client.get("/api/v1/auth/verification-status")
            assert final_status.status_code == 200, final_status.text
            assert final_status.json()["verified"] is True
            assert final_status.json()["can_process"] is True
    finally:
        settings.email_verification_resend_cooldown_seconds = original_cooldown
        _requests.clear()
        _auth_requests.clear()

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_one, init_db
from app.main import app
from app.services.billing import razorpay_request
from app.services.legal import (
    LEGAL_VERSION,
    init_legal_compliance,
    legal_configuration_issues,
    record_legal_acceptance,
)


async def _seed_user(user_id: str = "legal-user") -> None:
    await execute(
        """INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at)
           VALUES (?,?,?,?,'free','creator',1,?,?)""",
        (user_id, "Legal Creator", f"{user_id}@clipkaro.test", "hash", "2026-08-08T00:00:00+00:00", "2026-08-08T00:00:00+00:00"),
    )


def _configure_public_legal(settings, monkeypatch) -> None:
    values = {
        "legal_operator_name": "ClipKaro Test Operator",
        "legal_operator_address": "1 Test Road, Pune, Maharashtra 411001, India",
        "legal_contact_email": "legal@clipkaro.test",
        "privacy_contact_email": "privacy@clipkaro.test",
        "customer_care_email": "support@clipkaro.test",
        "customer_care_phone": "+91 9000000000",
        "grievance_officer_name": "Test Grievance Officer",
        "grievance_email": "grievance@clipkaro.test",
        "grievance_phone": "+91 9000000001",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


@pytest.mark.asyncio
async def test_paid_checkout_is_fail_closed_until_config_and_current_acceptance(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "database_path", tmp_path / "legal.db")
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    monkeypatch.setattr(settings, "app_env", "staging")
    await init_db()
    await _seed_user()

    await init_legal_compliance()
    assert legal_configuration_issues()
    with pytest.raises(Exception, match="LEGAL_CONFIGURATION_REQUIRED"):
        await execute(
            """INSERT INTO billing_checkouts(id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at)
               VALUES ('checkout-1','legal-user','one_time','mini_pass','order-1',5900,'created',NULL,'2026-08-08T00:00:00+00:00',NULL)"""
        )

    _configure_public_legal(settings, monkeypatch)
    await init_legal_compliance()
    assert legal_configuration_issues() == []
    with pytest.raises(Exception, match="LEGAL_ACCEPTANCE_REQUIRED"):
        await execute(
            """INSERT INTO billing_checkouts(id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at)
               VALUES ('checkout-2','legal-user','one_time','mini_pass','order-2',5900,'created',NULL,'2026-08-08T00:00:00+00:00',NULL)"""
        )

    accepted = await record_legal_acceptance("legal-user", LEGAL_VERSION, source="test", user_agent="pytest")
    assert accepted["accepted"] is True
    await execute(
        """INSERT INTO billing_checkouts(id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at)
           VALUES ('checkout-3','legal-user','one_time','mini_pass','order-3',5900,'created',NULL,'2026-08-08T00:00:00+00:00',NULL)"""
    )
    assert await fetch_one("SELECT id FROM billing_checkouts WHERE id='checkout-3'")


@pytest.mark.asyncio
async def test_razorpay_user_checkout_is_blocked_before_network_call(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "database_path", tmp_path / "provider-gate.db")
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "razorpay_mode", "test")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_public")
    monkeypatch.setattr(settings, "razorpay_key_secret", "test-secret")
    monkeypatch.setattr(settings, "allow_live_razorpay_in_development", False)
    await init_db()
    await _seed_user("provider-user")
    await init_legal_compliance()

    with patch("app.services.billing.httpx.AsyncClient.request", new=AsyncMock()) as request_mock:
        with pytest.raises(RuntimeError, match="LEGAL_CHECKOUT_NOT_ALLOWED"):
            await razorpay_request(
                "POST",
                "/orders",
                json_body={"amount": 5900, "currency": "INR", "notes": {"user_id": "provider-user", "plan": "mini_pass"}},
            )
        request_mock.assert_not_awaited()

    _configure_public_legal(settings, monkeypatch)
    await init_legal_compliance()
    with patch("app.services.billing.httpx.AsyncClient.request", new=AsyncMock()) as request_mock:
        with pytest.raises(RuntimeError, match="LEGAL_ACCEPTANCE_REQUIRED"):
            await razorpay_request(
                "POST",
                "/subscriptions",
                json_body={"plan_id": "plan_test", "notes": {"user_id": "provider-user", "plan": "growth"}},
            )
        request_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_legal_version_cannot_be_recorded(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "database_path", tmp_path / "stale.db")
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    await init_db()
    await _seed_user("stale-user")
    with pytest.raises(ValueError, match="no longer current"):
        await record_legal_acceptance("stale-user", "2025-01-01", source="test")


def test_authenticated_privacy_export_and_deletion_request(tmp_path):
    settings = get_settings()
    settings.database_path = tmp_path / "privacy-api.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "legal-privacy-test-secret"
    settings.seed_demo_user = True
    settings.app_env = "test"
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={"email": settings.demo_email, "password": settings.demo_password})
        assert login.status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")

        exported = client.get("/api/v1/privacy/export")
        assert exported.status_code == 200
        payload = exported.json()
        assert payload["account"]["email"] == settings.demo_email
        assert "password_hash" not in payload["account"]
        assert "server-side media file paths" in payload["excluded"]

        requested = client.post(
            "/api/v1/privacy/requests",
            json={"kind": "deletion", "details": "Delete my account after required retention checks."},
        )
        assert requested.status_code == 202
        assert requested.json()["status"] == "received"
        listed = client.get("/api/v1/privacy/requests")
        assert listed.status_code == 200
        assert listed.json()["requests"][0]["kind"] == "deletion"

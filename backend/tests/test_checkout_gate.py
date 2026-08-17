from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_one, init_db
from app.main import _auth_requests, _requests, app
from app.services.billing import (
    verify_order_signature,
    verify_subscription_signature,
)
from app.services.legal import (
    LEGAL_VERSION,
    checkout_allowed,
    init_legal_compliance,
    paid_launch_ready,
    record_legal_acceptance,
)

START = "2026-08-01T00:00:00+00:00"
END = "2026-09-01T00:00:00+00:00"


_LEGAL_KEYS = (
    "legal_operator_name",
    "legal_operator_address",
    "legal_contact_email",
    "privacy_contact_email",
    "customer_care_email",
    "customer_care_phone",
    "grievance_officer_name",
    "grievance_email",
    "grievance_phone",
)

_FULL_LEGAL = {
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


def _legal(settings, *, complete: bool, monkeypatch) -> None:
    values = {key: "" for key in _LEGAL_KEYS}
    if complete:
        values.update(_FULL_LEGAL)
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def _mode(settings, *, mode: str, key: str, monkeypatch) -> None:
    monkeypatch.setattr(settings, "razorpay_mode", mode)
    monkeypatch.setattr(settings, "razorpay_key_id", key)
    monkeypatch.setattr(settings, "razorpay_key_secret", "secret")


class TestCheckoutPolicyMatrix:
    """Deterministic deployment matrix for the canonical checkout gate."""

    def test_development_test_mode_incomplete_legal_allowed(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")
        _legal(settings, complete=False, monkeypatch=monkeypatch)
        _mode(settings, mode="test", key="rzp_test_abc", monkeypatch=monkeypatch)
        assert paid_launch_ready() is False
        assert checkout_allowed() == (True, "Test mode in development environment")

    def test_development_live_mode_incomplete_legal_blocked_by_default(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "allow_live_razorpay_in_development", False)
        _legal(settings, complete=False, monkeypatch=monkeypatch)
        _mode(settings, mode="live", key="rzp_live_abc", monkeypatch=monkeypatch)
        assert paid_launch_ready() is False
        allowed, reason = checkout_allowed()
        assert allowed is False
        assert "legal" in reason.lower()

    def test_development_live_mode_explicit_opt_in_allows_local_checkout(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "allow_live_razorpay_in_development", True)
        _legal(settings, complete=False, monkeypatch=monkeypatch)
        _mode(settings, mode="live", key="rzp_live_abc", monkeypatch=monkeypatch)
        assert paid_launch_ready() is False
        assert checkout_allowed() == (True, "Live Razorpay explicitly enabled for local development")

    def test_production_test_mode_fails_closed_without_legal(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        _legal(settings, complete=False, monkeypatch=monkeypatch)
        _mode(settings, mode="test", key="rzp_test_abc", monkeypatch=monkeypatch)
        assert paid_launch_ready() is False
        allowed, reason = checkout_allowed()
        assert allowed is False
        assert "legal" in reason.lower()

    def test_production_live_mode_incomplete_legal_blocked(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        _legal(settings, complete=False, monkeypatch=monkeypatch)
        _mode(settings, mode="live", key="rzp_live_abc", monkeypatch=monkeypatch)
        assert paid_launch_ready() is False
        allowed, reason = checkout_allowed()
        assert allowed is False
        assert "legal" in reason.lower()

    def test_production_live_mode_complete_legal_allowed(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        _legal(settings, complete=True, monkeypatch=monkeypatch)
        _mode(settings, mode="live", key="rzp_live_abc", monkeypatch=monkeypatch)
        assert paid_launch_ready() is True
        assert checkout_allowed() == (True, "Live mode with complete legal config")

    def test_mode_key_mismatch_blocked(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")
        _legal(settings, complete=True, monkeypatch=monkeypatch)
        _mode(settings, mode="test", key="rzp_live_abc", monkeypatch=monkeypatch)
        assert settings.razorpay_mode_key_consistent is False
        allowed, reason = checkout_allowed()
        assert allowed is False
        assert "does not match" in reason

    def test_live_mode_with_test_key_blocked(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "development")
        _legal(settings, complete=True, monkeypatch=monkeypatch)
        _mode(settings, mode="live", key="rzp_test_abc", monkeypatch=monkeypatch)
        assert settings.razorpay_mode_key_consistent is False
        assert checkout_allowed()[0] is False


class TestCheckoutEndpointEnforcement:
    """Direct API enforcement: the endpoint must independently allow dev+test."""

    @pytest.fixture(autouse=True)
    def _clear_rate_limiter_state(self):
        _requests.clear()
        _auth_requests.clear()
        yield
        _requests.clear()
        _auth_requests.clear()

    def _settings(self, tmp_path, monkeypatch):
        settings = get_settings()
        values = {
            "app_env": "development",
            "database_path": tmp_path / "checkout-gate.db",
            "storage_root": tmp_path / "storage",
            "secret_key": "checkout-gate-secret",
            "seed_demo_user": True,
            "razorpay_mode": "test",
            "razorpay_key_id": "rzp_test_public",
            "razorpay_key_secret": "test-secret",
            "razorpay_webhook_secret": "webhook-secret",
            "allow_live_razorpay_in_development": False,
        }
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)
        return settings

    @staticmethod
    def _accept(client: TestClient) -> None:
        response = client.post("/api/v1/legal/accept", json={"accepted": True, "version": LEGAL_VERSION})
        assert response.status_code == 200, response.text

    def test_checkout_endpoint_allows_test_mode_development(self, tmp_path, monkeypatch):
        settings = self._settings(tmp_path, monkeypatch)
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login",
                                json={"email": settings.demo_email, "password": settings.demo_password})
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
            self._accept(client)

            with patch("app.api.billing_lifecycle.razorpay_request",
                       new=AsyncMock(return_value={"id": "order_test_gate"})), \
                 patch("app.api.billing_lifecycle.ensure_razorpay_plan",
                       new=AsyncMock(return_value="plan_test_gate")):
                checkout = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
            assert checkout.status_code == 200
            assert checkout.json()["kind"] == "one_time"
            assert checkout.json()["order_id"] == "order_test_gate"

    def test_direct_paid_checkout_requires_current_user_acceptance_even_in_development(self, tmp_path, monkeypatch):
        settings = self._settings(tmp_path, monkeypatch)
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": settings.demo_email, "password": settings.demo_password},
            )
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
            blocked = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
            assert blocked.status_code == 403
            assert "accept" in blocked.json()["detail"].lower()

    def test_checkout_endpoint_allows_explicit_live_mode_local_development(self, tmp_path, monkeypatch):
        settings = self._settings(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "razorpay_mode", "live")
        monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_public")
        monkeypatch.setattr(settings, "allow_live_razorpay_in_development", True)
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login",
                                json={"email": settings.demo_email, "password": settings.demo_password})
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
            self._accept(client)

            with patch("app.api.billing_lifecycle.razorpay_request",
                       new=AsyncMock(return_value={"id": "order_live_dev"})):
                checkout = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
            assert checkout.status_code == 200
            assert checkout.json()["order_id"] == "order_live_dev"

    def test_checkout_endpoint_blocks_live_incomplete_legal(self, tmp_path, monkeypatch):
        settings = self._settings(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "app_env", "staging")
        monkeypatch.setattr(settings, "razorpay_mode", "live")
        monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_public")
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login",
                                json={"email": settings.demo_email, "password": settings.demo_password})
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")

            checkout = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
            assert checkout.status_code == 403
            assert "legal" in checkout.json()["detail"].lower()

    def test_legal_status_exposes_checkout_mode_for_frontend(self, tmp_path, monkeypatch):
        settings = self._settings(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "app_env", "development")
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login",
                                json={"email": settings.demo_email, "password": settings.demo_password})
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
            status = client.get("/api/v1/legal/status")
            assert status.status_code == 200
            payload = status.json()
            assert payload["razorpay_mode"] == "test"
            assert payload["checkout_allowed"] is True
            assert payload["paid_launch_ready"] is False


class TestUnchangedProtections:
    """Signature, webhook and entitlement behaviour must not change."""

    def test_order_signature_verification_unchanged(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "razorpay_key_secret", "unittest-secret")
        valid = hmac.new(
            b"unittest-secret", b"order_1|pay_1", hashlib.sha256
        ).hexdigest()
        assert verify_order_signature("order_1", "pay_1", valid) is True
        assert verify_order_signature("order_1", "pay_1", "bad") is False

    def test_subscription_signature_verification_unchanged(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "razorpay_key_secret", "unittest-secret")
        valid = hmac.new(
            b"unittest-secret", b"pay_1|sub_1", hashlib.sha256
        ).hexdigest()
        assert verify_subscription_signature("sub_1", "pay_1", valid) is True
        assert verify_subscription_signature("sub_1", "pay_1", "bad") is False

    def test_checkout_trigger_still_requires_acceptance_in_staging(self, tmp_path, monkeypatch):
        import asyncio

        settings = get_settings()
        monkeypatch.setattr(settings, "database_path", tmp_path / "gate-staging.db")
        monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
        monkeypatch.setattr(settings, "app_env", "staging")
        _legal(settings, complete=True, monkeypatch=monkeypatch)
        asyncio.run(init_db())
        asyncio.run(execute(
            """INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at)
               VALUES ('gate-user','Gate Creator','gate@clipkaro.test','hash','free','creator',1,?,?)""",
            (START, START),
        ))
        asyncio.run(init_legal_compliance())
        with pytest.raises(Exception, match="LEGAL_ACCEPTANCE_REQUIRED"):
            asyncio.run(execute(
                """INSERT INTO billing_checkouts(id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at)
                   VALUES ('gate-1','gate-user','one_time','mini_pass','order-gate',5900,'created',NULL,?,NULL)""",
                (START,),
            ))

    def test_entitlement_plan_activation_unchanged(self, tmp_path, monkeypatch):
        from app.services.billing import activate_entitlement

        settings = get_settings()
        monkeypatch.setattr(settings, "database_path", tmp_path / "gate-entitle.db")
        monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
        import asyncio

        asyncio.run(init_db())
        asyncio.run(execute(
            """INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at)
               VALUES ('entitle-user','Entitle Creator','entitle@clipkaro.test','hash','free','creator',1,?,?)""",
            (START, START),
        ))
        asyncio.run(activate_entitlement("entitle-user", "mini_pass", "order-entitle"))
        row = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id='entitle-user'"))
        assert row["plan"] == "mini_pass"
        assert row["billing_reference"] == "order-entitle"
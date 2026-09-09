from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from app.api import creator_pulse
from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one, init_db
from app.main import app


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def pulse_db(tmp_path: Path):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_backend": settings.database_backend,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "seed_demo_user": settings.seed_demo_user,
    }
    settings.app_env = "test"
    settings.database_backend = "sqlite"
    settings.database_path = tmp_path / "creator-pulse.db"
    settings.storage_root = tmp_path / "storage"
    settings.seed_demo_user = False
    run(init_db())
    run(creator_pulse.init_creator_pulse())
    user_id = "pulse-user"
    now = creator_pulse.utc_now().isoformat()
    run(execute(
        "INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at) VALUES (?,?,?,?, 'free','creator',1,?,?)",
        (user_id, "Pulse Creator", "pulse@example.com", "test-hash", now, now),
    ))
    run(creator_pulse._ensure_wallet(user_id))
    try:
        yield user_id
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def snapshot(channel_id: str = "UC_TEST") -> dict:
    return {
        "channel": {
            "id": channel_id,
            "handle": "@testcreator",
            "title": "Test Creator",
            "description": "",
            "thumbnail_url": None,
            "subscribers": 1000,
            "hidden_subscriber_count": False,
            "total_views": 25000,
            "video_count": 42,
        },
        "recent": {
            "average_views": 1500,
            "average_engagement_rate": 4.2,
            "upload_cadence_days": 2.0,
            "videos": [
                {
                    "id": "v1",
                    "title": "Fast video",
                    "published_at": "2026-09-08T00:00:00Z",
                    "thumbnail_url": None,
                    "views": 2000,
                    "likes": 80,
                    "comments": 20,
                    "age_days": 1.0,
                    "views_per_day": 2000.0,
                    "engagement_rate": 5.0,
                    "vs_recent_average_pct": 33.33,
                },
                {
                    "id": "v2",
                    "title": "Slow video",
                    "published_at": "2026-09-05T00:00:00Z",
                    "thumbnail_url": None,
                    "views": 1000,
                    "likes": 30,
                    "comments": 10,
                    "age_days": 4.0,
                    "views_per_day": 250.0,
                    "engagement_rate": 4.0,
                    "vs_recent_average_pct": -33.33,
                },
            ],
        },
    }


def set_balance(user_id: str, paise: int) -> None:
    run(execute("UPDATE creator_pulse_wallets SET balance_paise=?,updated_at=? WHERE user_id=?", (paise, creator_pulse.utc_now().isoformat(), user_id)))


def test_routes_are_registered():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v1/creator-pulse/status" in paths
    assert "/api/v1/creator-pulse/analyse" in paths
    assert "/api/v1/creator-pulse/balance/checkout" in paths
    assert "/api/v1/creator-pulse/balance/verify" in paths


def test_one_rupee_reservation_and_provider_failure_refund_are_atomic(pulse_db: str):
    set_balance(pulse_db, 1000)
    request_key = str(uuid.uuid4())
    scan_id = run(creator_pulse._reserve_pulse(pulse_db, "@testcreator", request_key))
    assert run(creator_pulse._wallet_balance(pulse_db)) == 900
    charge = run(fetch_one("SELECT * FROM creator_pulse_transactions WHERE reference=?", (f"pulse:{request_key}",)))
    assert charge and charge["delta_paise"] == -100 and charge["balance_after_paise"] == 900

    run(creator_pulse._refund_pulse(scan_id, request_key, "YOUTUBE_UNAVAILABLE"))
    assert run(creator_pulse._wallet_balance(pulse_db)) == 1000
    failed = run(fetch_one("SELECT * FROM creator_pulse_scans WHERE id=?", (scan_id,)))
    assert failed and failed["status"] == "failed" and failed["charged_paise"] == 0
    refund = run(fetch_one("SELECT * FROM creator_pulse_transactions WHERE reference=?", (f"refund:{request_key}",)))
    assert refund and refund["delta_paise"] == 100 and refund["balance_after_paise"] == 1000

    # Retrying refund is idempotent: no second ₹1 is created.
    run(creator_pulse._refund_pulse(scan_id, request_key, "YOUTUBE_UNAVAILABLE"))
    assert run(creator_pulse._wallet_balance(pulse_db)) == 1000
    refunds = run(fetch_all("SELECT * FROM creator_pulse_transactions WHERE reference=?", (f"refund:{request_key}",)))
    assert len(refunds) == 1


def test_successful_pulse_charges_once_and_same_request_returns_saved_truth(pulse_db: str, monkeypatch: pytest.MonkeyPatch):
    set_balance(pulse_db, 1000)

    async def fake_snapshot(handle: str):
        assert handle == "@testcreator"
        return snapshot()

    monkeypatch.setattr(creator_pulse, "_youtube_api_key", lambda: "configured-for-test")
    monkeypatch.setattr(creator_pulse, "_fetch_youtube_snapshot", fake_snapshot)
    request_key = str(uuid.uuid4())
    user = {"id": pulse_db, "name": "Pulse Creator", "email": "pulse@example.com"}
    body = {"handle": "@testcreator", "request_key": request_key}

    first = run(creator_pulse.creator_pulse_analyse(body, user))
    assert first["charged_paise"] == 100
    assert first["balance_paise"] == 900
    assert first["channel"]["total_views"] == 25000

    second = run(creator_pulse.creator_pulse_analyse(body, user))
    assert second["id"] == first["id"]
    assert second["balance_paise"] == 900
    charges = run(fetch_all("SELECT * FROM creator_pulse_transactions WHERE reference=?", (f"pulse:{request_key}",)))
    assert len(charges) == 1


def test_topup_credit_is_idempotent_and_does_not_change_subscription_plan(pulse_db: str):
    order_id = "order_pulse_test"
    checkout_id = "pulse-checkout"
    now = creator_pulse.utc_now().isoformat()
    run(execute(
        "INSERT INTO creator_pulse_checkouts(id,user_id,provider_reference,amount_paise,status,payment_id,created_at,verified_at) VALUES (?,?,?,?, 'created',NULL,?,NULL)",
        (checkout_id, pulse_db, order_id, 2000, now),
    ))

    first = run(creator_pulse._credit_verified_checkout(checkout_id, payment_id="pay_test"))
    second = run(creator_pulse._credit_verified_checkout(checkout_id, payment_id="pay_test"))
    assert first == (True, 2000, 2000)
    assert second == (False, 2000, 2000)
    assert run(creator_pulse._wallet_balance(pulse_db)) == 2000
    ledger = run(fetch_all("SELECT * FROM creator_pulse_transactions WHERE reference=?", (f"topup:{order_id}",)))
    assert len(ledger) == 1
    user = run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (pulse_db,)))
    assert user and user["plan"] == "free" and not user["billing_reference"]


def test_signed_webhook_reconciliation_credits_captured_pulse_order_once(pulse_db: str):
    order_id = "order_webhook_pulse"
    checkout_id = "pulse-webhook-checkout"
    now = creator_pulse.utc_now().isoformat()
    run(execute(
        "INSERT INTO creator_pulse_checkouts(id,user_id,provider_reference,amount_paise,status,payment_id,created_at,verified_at) VALUES (?,?,?,?, 'created',NULL,?,NULL)",
        (checkout_id, pulse_db, order_id, 1000, now),
    ))
    payment = {"id": "pay_webhook", "order_id": order_id, "amount": 1000, "currency": "INR", "status": "captured", "captured": True}
    first = run(creator_pulse.reconcile_creator_pulse_webhook("payment.captured", payment, {}))
    second = run(creator_pulse.reconcile_creator_pulse_webhook("payment.captured", payment, {}))
    assert first and first["status"] == "verified"
    assert second and second["status"] == "verified"
    assert run(creator_pulse._wallet_balance(pulse_db)) == 1000
    ledger = run(fetch_all("SELECT * FROM creator_pulse_transactions WHERE reference=?", (f"topup:{order_id}",)))
    assert len(ledger) == 1


def test_insights_are_deterministic_and_evidence_based():
    insights = creator_pulse._build_insights(snapshot())
    assert insights[0]["key"] == "momentum"
    assert insights[0]["title"] == "Fast video"
    assert any(item["key"] == "engagement" for item in insights)
    assert any(item["key"] == "below_average" for item in insights)
    assert all("AI" not in json.dumps(item) for item in insights)

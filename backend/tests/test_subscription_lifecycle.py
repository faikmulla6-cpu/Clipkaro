from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import billing_lifecycle as billing_lifecycle_module
from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.main import _auth_requests, _requests, app
from app.services import billing as billing_module
from app.services.legal import LEGAL_VERSION, record_legal_acceptance

START = "2026-08-01T00:00:00+00:00"
END = "2026-09-01T00:00:00+00:00"
NEXT_END = "2026-10-01T00:00:00+00:00"
START_EPOCH = 1785542400
END_EPOCH = 1788220800
NEXT_END_EPOCH = 1790812800
FIXED_BILLING_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_billing_clock(monkeypatch):
    """Keep lifecycle fixtures deterministic without depending on host wall clock."""
    monkeypatch.setattr(billing_lifecycle_module, "utc_now", lambda: FIXED_BILLING_NOW)
    monkeypatch.setattr(billing_module, "utc_now", lambda: FIXED_BILLING_NOW)


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
        "razorpay_mode": settings.razorpay_mode,
        "razorpay_key_id": settings.razorpay_key_id,
        "razorpay_key_secret": settings.razorpay_key_secret,
        "razorpay_webhook_secret": settings.razorpay_webhook_secret,
    }
    settings.app_env = "test"
    settings.database_path = tmp_path / "subscription-lifecycle.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = False
    settings.razorpay_mode = "test"
    settings.razorpay_key_id = "rzp_test_public"
    settings.razorpay_key_secret = "test-secret"
    settings.razorpay_webhook_secret = "webhook-secret"
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


def signup(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/signup",
        json={"name": "Billing Creator", "email": email, "password": "Secure123"},
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    user_id = response.json()["user"]["id"]
    asyncio.run(record_legal_acceptance(user_id, LEGAL_VERSION, source="test"))
    return user_id


async def seed_plan_map() -> None:
    rows = [
        ("creator", "plan_creator", 19900),
        ("growth", "plan_growth", 39900),
        ("pro", "plan_pro", 79900),
        ("agency", "plan_agency", 199900),
    ]
    for plan, provider, amount in rows:
        await execute(
            "INSERT OR REPLACE INTO billing_plans(plan_key,provider_plan_id,amount,currency,created_at) VALUES (?,?,?,?,?)",
            (plan, provider, amount, "INR", START),
        )


async def make_recurring(user_id: str, plan: str, subscription_id: str) -> None:
    await seed_plan_map()
    await execute(
        """UPDATE users SET plan=?,billing_reference=?,plan_started_at=?,plan_expires_at=?,
           cancel_at_period_end=0 WHERE id=?""",
        (plan, subscription_id, START, END, user_id),
    )


def entity(subscription_id: str, plan_id: str, *, start: int = START_EPOCH, end: int = END_EPOCH,
           scheduled: bool = False, scheduled_at: int | None = None, status: str = "active") -> dict:
    return {
        "id": subscription_id,
        "plan_id": plan_id,
        "status": status,
        "current_start": start,
        "current_end": end,
        "paid_count": 1,
        "has_scheduled_changes": scheduled,
        "change_scheduled_at": scheduled_at,
        "schedule_change_at": "cycle_end" if scheduled else None,
        "notes": {"user_id": "ignored-by-tests"},
    }


def test_immediate_upgrade_preserves_current_cycle_usage_and_reservations(client: TestClient):
    user_id = signup(client, "upgrade@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_upgrade"))
    old_key = "creator:sub_upgrade:2026-08-01T00:00:00"
    new_key = "growth:sub_upgrade:2026-08-01T00:00:00"
    asyncio.run(execute(
        "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?,?,?,?,?,?)",
        ("usage-old", user_id, old_key, 50.0, 10, 15),
    ))
    asyncio.run(execute(
        """INSERT INTO usage_reservations(id,user_id,period_key,kind,amount,resource_id,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("reservation-old", user_id, old_key, "minutes", 5.0, "project-in-flight", "reserved", START, START),
    ))

    asyncio.run(execute(
        """INSERT INTO short_credit_reservations
           (clip_id,user_id,period_key,export_id,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        ("upgrade-finished",user_id,old_key,"upgrade-export","finalized",START,START),
    ))
    calls: list[tuple[str, str, dict]] = []

    async def provider(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return entity("sub_upgrade", "plan_creator")
        if method == "PATCH":
            assert kwargs["json_body"]["plan_id"] == "plan_growth"
            assert kwargs["json_body"]["schedule_change_at"] == "now"
            return entity("sub_upgrade", "plan_growth")
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)), \
         patch("app.api.billing_lifecycle.ensure_razorpay_plan", new=AsyncMock(return_value="plan_growth")):
        response = client.post("/api/v1/billing/checkout", json={"plan": "growth"})

    assert response.status_code == 200
    assert response.json()["change"] == "immediate_upgrade"
    assert response.json()["plan"] == "growth"
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "growth" and user["billing_reference"] == "sub_upgrade"
    assert asyncio.run(fetch_one("SELECT id FROM usage WHERE user_id=? AND month=?", (user_id, old_key))) is None
    moved = asyncio.run(fetch_one("SELECT * FROM usage WHERE user_id=? AND month=?", (user_id, new_key)))
    assert moved and moved["source_minutes"] == 50.0 and moved["exports_used"] == 10 and moved["exports_limit"] == 50
    reservation = asyncio.run(fetch_one("SELECT * FROM usage_reservations WHERE id='reservation-old'"))
    assert reservation and reservation["period_key"] == new_key
    usage = client.get("/api/v1/usage").json()
    assert usage["processing_minutes_remaining"] == 250.0
    slot = asyncio.run(fetch_one("SELECT period_key FROM short_credit_reservations WHERE clip_id='upgrade-finished'"))
    assert slot and slot["period_key"] == new_key
    assert usage["shorts_used"] == 1
    assert usage["shorts_remaining"] == 49
    assert usage["unlimited_exports"] is True
    assert any(call[0] == "PATCH" for call in calls)


def test_lower_recurring_plan_is_scheduled_without_reducing_current_limits(client: TestClient):
    user_id = signup(client, "downgrade@example.com")
    asyncio.run(make_recurring(user_id, "pro", "sub_downgrade"))
    old_key = "pro:sub_downgrade:2026-08-01T00:00:00"
    asyncio.run(execute(
        "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?,?,?,?,?,?)",
        ("usage-pro", user_id, old_key, 200.0, 40, 150),
    ))

    async def provider(method, path, **kwargs):
        if method == "GET":
            return entity("sub_downgrade", "plan_pro")
        if method == "PATCH":
            assert kwargs["json_body"]["plan_id"] == "plan_growth"
            assert kwargs["json_body"]["schedule_change_at"] == "cycle_end"
            return entity("sub_downgrade", "plan_pro", scheduled=True, scheduled_at=END_EPOCH)
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)), \
         patch("app.api.billing_lifecycle.ensure_razorpay_plan", new=AsyncMock(return_value="plan_growth")):
        response = client.post("/api/v1/billing/checkout", json={"plan": "growth"})

    assert response.status_code == 200 and response.json()["change"] == "scheduled_downgrade"
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "pro" and user["cancel_at_period_end"] == 0
    pending = asyncio.run(fetch_one("SELECT * FROM subscription_plan_changes WHERE user_id=?", (user_id,)))
    assert pending and pending["to_plan"] == "growth" and pending["change_kind"] == "downgrade"
    usage = client.get("/api/v1/usage").json()
    assert usage["processing_minutes_limit"] == 600
    assert usage["processing_minutes_remaining"] == 400.0
    assert usage["source_minutes_per_short"] == 180
    status = client.get("/api/v1/billing/status").json()
    assert status["plan"] == "pro"
    assert status["scheduled_plan"] == "growth"
    assert status["cancel_at_period_end"] is False


def test_scheduled_downgrade_applies_when_provider_moves_to_next_cycle(client: TestClient):
    user_id = signup(client, "cycle@example.com")
    asyncio.run(make_recurring(user_id, "pro", "sub_cycle"))
    asyncio.run(execute(
        """INSERT INTO subscription_plan_changes(
             user_id,subscription_id,from_plan,to_plan,change_kind,provider_plan_id,effective_at,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, "sub_cycle", "pro", "growth", "downgrade", "plan_growth", END, START, START),
    ))

    async def provider(method, path, **kwargs):
        assert method == "GET" and path == "/subscriptions/sub_cycle"
        return entity("sub_cycle", "plan_growth", start=END_EPOCH, end=NEXT_END_EPOCH)

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)):
        response = client.post("/api/v1/billing/sync", json={})

    assert response.status_code == 200
    assert response.json()["plan"] == "growth"
    assert response.json()["scheduled_plan"] is None
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "growth" and user["plan_started_at"].startswith("2026-09-01")
    assert asyncio.run(fetch_one("SELECT * FROM subscription_plan_changes WHERE user_id=?", (user_id,))) is None


def test_scheduled_downgrade_can_be_cancelled_without_cancelling_subscription(client: TestClient):
    user_id = signup(client, "keep-pro@example.com")
    asyncio.run(make_recurring(user_id, "pro", "sub_keep"))
    asyncio.run(execute(
        """INSERT INTO subscription_plan_changes(
             user_id,subscription_id,from_plan,to_plan,change_kind,provider_plan_id,effective_at,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, "sub_keep", "pro", "growth", "downgrade", "plan_growth", END, START, START),
    ))

    provider = AsyncMock(return_value=entity("sub_keep", "plan_pro"))
    with patch("app.api.billing_lifecycle.razorpay_request", new=provider):
        response = client.post("/api/v1/billing/cancel-scheduled-change", json={})

    assert response.status_code == 200 and response.json()["plan"] == "pro"
    assert response.json()["scheduled_plan"] is None
    assert asyncio.run(fetch_one("SELECT * FROM subscription_plan_changes WHERE user_id=?", (user_id,))) is None
    assert any(call.args[0] == "POST" and call.args[1].endswith("/cancel_scheduled_changes") for call in provider.await_args_list)


def test_downgrade_to_free_schedules_cycle_end_cancellation_and_blocks_reactivation(client: TestClient):
    user_id = signup(client, "free-next@example.com")
    asyncio.run(make_recurring(user_id, "growth", "sub_free_next"))

    async def provider(method, path, **kwargs):
        if method == "GET":
            return entity("sub_free_next", "plan_growth")
        if method == "POST" and path.endswith("/cancel"):
            assert kwargs["json_body"] == {"cancel_at_cycle_end": True}
            return entity("sub_free_next", "plan_growth", scheduled=True, scheduled_at=END_EPOCH)
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)):
        response = client.post("/api/v1/billing/checkout", json={"plan": "free"})
    assert response.status_code == 200 and response.json()["change"] == "scheduled_cancellation"
    status = client.get("/api/v1/billing/status").json()
    assert status["plan"] == "growth" and status["scheduled_plan"] == "free"
    assert status["cancel_at_period_end"] is True and status["scheduled_change_type"] == "cancel"

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)):
        blocked = client.post("/api/v1/billing/checkout", json={"plan": "pro"})
    assert blocked.status_code == 409
    assert "scheduled to end" in blocked.json()["detail"]


def test_mini_pass_cannot_replace_an_active_recurring_mandate(client: TestClient):
    user_id = signup(client, "mini-block@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_mini_block"))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(return_value=entity("sub_mini_block", "plan_creator"))):
        response = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
    assert response.status_code == 422
    assert "one-time pass" in response.json()["detail"]


def test_provider_failure_does_not_change_local_plan(client: TestClient):
    user_id = signup(client, "provider-failure@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_provider_failure"))

    async def provider(method, path, **kwargs):
        if method == "GET":
            return entity("sub_provider_failure", "plan_creator")
        if method == "PATCH":
            raise RuntimeError("provider unavailable")
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)), \
         patch("app.api.billing_lifecycle.ensure_razorpay_plan", new=AsyncMock(return_value="plan_growth")):
        response = client.post("/api/v1/billing/checkout", json={"plan": "growth"})
    assert response.status_code == 502
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "creator"
    assert asyncio.run(fetch_one("SELECT * FROM subscription_plan_changes WHERE user_id=?", (user_id,))) is None


def test_webhook_uses_provider_plan_id_not_stale_subscription_notes(client: TestClient):
    user_id = signup(client, "webhook-plan@example.com")
    asyncio.run(make_recurring(user_id, "pro", "sub_webhook_plan"))
    asyncio.run(execute(
        """INSERT INTO subscription_plan_changes(
             user_id,subscription_id,from_plan,to_plan,change_kind,provider_plan_id,effective_at,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, "sub_webhook_plan", "pro", "growth", "downgrade", "plan_growth", END, START, START),
    ))

    payload = {
        "event_id": "evt_plan_changed",
        "event": "subscription.charged",
        "payload": {
            "subscription": {"entity": {
                **entity("sub_webhook_plan", "plan_growth", start=END_EPOCH, end=NEXT_END_EPOCH),
                "notes": {"user_id": user_id, "plan": "pro"},
            }},
            "payment": {"entity": {"id": "pay_new_cycle", "amount": 39900, "status": "captured"}},
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    secret = get_settings().razorpay_webhook_secret
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    first = client.post(
        "/api/v1/billing/razorpay/webhook", content=raw,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    second = client.post(
        "/api/v1/billing/razorpay/webhook", content=raw,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert first.status_code == second.status_code == 204
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "growth"
    events = asyncio.run(fetch_all("SELECT * FROM payment_events WHERE provider_event_id='evt_plan_changed'"))
    assert len(events) == 1 and events[0]["plan"] == "growth"


def _post_subscription_webhook(client: TestClient, payload: dict, event_id: str):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    secret = get_settings().razorpay_webhook_secret
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/billing/razorpay/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
        },
    )


def test_subscription_webhook_ignores_older_out_of_order_plan_event(client: TestClient):
    user_id = signup(client, "ordering@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_ordering"))

    newer = {
        "event": "subscription.updated",
        "created_at": 200,
        "payload": {"subscription": {"entity": entity("sub_ordering", "plan_growth", status="active")}},
    }
    first = _post_subscription_webhook(client, newer, "evt_ordering_new")
    assert first.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "growth"

    older = {
        "event": "subscription.updated",
        "created_at": 100,
        "payload": {"subscription": {"entity": entity("sub_ordering", "plan_creator", status="active")}},
    }
    second = _post_subscription_webhook(client, older, "evt_ordering_old")
    assert second.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "growth"
    event = asyncio.run(fetch_one(
        "SELECT status FROM payment_events WHERE provider_event_id='evt_ordering_old'"
    ))
    assert event and event["status"] == "ignored_out_of_order"


def test_terminal_subscription_webhook_cannot_be_reactivated_by_later_stale_event(client: TestClient):
    user_id = signup(client, "terminal@example.com")
    asyncio.run(make_recurring(user_id, "growth", "sub_terminal"))

    cancelled = {
        "event": "subscription.cancelled",
        "created_at": 300,
        "payload": {"subscription": {"entity": entity("sub_terminal", "plan_growth", status="cancelled")}},
    }
    response = _post_subscription_webhook(client, cancelled, "evt_terminal_cancelled")
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "free" and not user["billing_reference"]

    # Even if a non-terminal delivery arrives later, the same cancelled provider
    # subscription id is terminal and must never grant paid access again.
    activated = {
        "event": "subscription.activated",
        "created_at": 301,
        "payload": {"subscription": {"entity": entity("sub_terminal", "plan_growth", status="active")}},
    }
    response = _post_subscription_webhook(client, activated, "evt_terminal_late_active")
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "free" and not user["billing_reference"]
    event = asyncio.run(fetch_one(
        "SELECT status FROM payment_events WHERE provider_event_id='evt_terminal_late_active'"
    ))
    assert event and event["status"] == "ignored_after_terminal"


def test_precharge_authenticated_webhook_does_not_grant_paid_entitlement(client: TestClient):
    user_id = signup(client, "precharge@example.com")
    asyncio.run(seed_plan_map())
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
        ("checkout-precharge", user_id, "subscription", "pro", "sub_precharge", 79900, START),
    ))
    authenticated_entity = {
        **entity("sub_precharge", "plan_pro", status="authenticated"),
        "paid_count": 0,
        "current_start": None,
        "current_end": None,
    }
    response = _post_subscription_webhook(client, {
        "event": "subscription.authenticated",
        "created_at": 400,
        "payload": {"subscription": {"entity": authenticated_entity}},
    }, "evt_precharge_authenticated")
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "free" and not user["billing_reference"]
    checkout = asyncio.run(fetch_one("SELECT status,verified_at FROM billing_checkouts WHERE id='checkout-precharge'"))
    assert checkout and checkout["status"] == "authorized" and checkout["verified_at"] is None

    active_entity = {
        **entity("sub_precharge", "plan_pro", status="active"),
        "paid_count": 1,
    }
    response = _post_subscription_webhook(client, {
        "event": "subscription.activated",
        "created_at": 401,
        "payload": {"subscription": {"entity": active_entity}},
    }, "evt_precharge_active")
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "pro" and user["billing_reference"] == "sub_precharge"
    checkout = asyncio.run(fetch_one("SELECT status,verified_at FROM billing_checkouts WHERE id='checkout-precharge'"))
    assert checkout and checkout["status"] == "verified" and checkout["verified_at"]


def test_pending_new_checkout_with_historical_paid_count_does_not_become_verified(client: TestClient):
    """A pending retry is failed-current-cycle truth, not initial activation."""
    user_id = signup(client, "pending-new-checkout@example.com")
    asyncio.run(seed_plan_map())
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
        ("checkout-pending-new", user_id, "subscription", "pro", "sub_pending_new", 79900, START),
    ))
    pending_entity = {
        **entity("sub_pending_new", "plan_pro", status="pending"),
        "paid_count": 1,
    }
    response = _post_subscription_webhook(client, {
        "event": "subscription.pending",
        "created_at": 450,
        "payload": {"subscription": {"entity": pending_entity}},
    }, "evt_pending_new_checkout")
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)))
    checkout = asyncio.run(fetch_one(
        "SELECT status,verified_at FROM billing_checkouts WHERE id='checkout-pending-new'"
    ))
    assert user and user["plan"] == "free" and not user["billing_reference"]
    assert checkout and checkout["status"] != "verified" and checkout["verified_at"] is None


def test_replayed_verified_checkout_reports_current_entitlement_not_historical_payment(client: TestClient):
    user_id = signup(client, "replayed-verified@example.com")
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'verified',?,?,?)""",
        (
            "checkout-old-mini", user_id, "one_time", "mini_pass", "order_old_mini", 5900,
            "pay_old_mini", START, END,
        ),
    ))
    # The paid pass has since expired/downgraded; the checkout remains valid
    # payment history but must not be reported as an active entitlement.
    asyncio.run(execute(
        "UPDATE users SET plan='free',billing_reference=NULL,plan_started_at=NULL,plan_expires_at=NULL WHERE id=?",
        (user_id,),
    ))
    response = client.post(
        "/api/v1/billing/verify",
        json={
            "razorpay_payment_id": "pay_old_mini",
            "razorpay_order_id": "order_old_mini",
            "razorpay_signature": "historical-idempotent-callback",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"verified": True, "activated": False, "plan": "mini_pass"}


def test_expired_paused_subscription_does_not_keep_paid_access_indefinitely(client: TestClient):
    user_id = signup(client, "expired-pause@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_expired_pause"))
    expired_end = 1735689600  # 2025-01-01 UTC, safely before this release.
    expired_start = 1733011200
    paused = {
        "event": "subscription.paused",
        "created_at": 499,
        "payload": {"subscription": {"entity": entity(
            "sub_expired_pause", "plan_creator", status="paused", start=expired_start, end=expired_end
        )}},
    }
    response = _post_subscription_webhook(client, paused, "evt_expired_pause")
    assert response.status_code == 204
    user = asyncio.run(fetch_one(
        "SELECT plan,billing_reference,plan_expires_at FROM users WHERE id=?", (user_id,)
    ))
    assert user and user["plan"] == "free" and user["billing_reference"] is None


def test_paused_subscription_preserves_paid_period_and_resumed_event_refreshes_state(client: TestClient):
    user_id = signup(client, "pause-resume@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_pause_resume"))

    paused = {
        "event": "subscription.paused",
        "created_at": 500,
        "payload": {"subscription": {"entity": entity(
            "sub_pause_resume", "plan_creator", status="paused", start=START_EPOCH, end=END_EPOCH
        )}},
    }
    response = _post_subscription_webhook(client, paused, "evt_pause")
    assert response.status_code == 204
    user = asyncio.run(fetch_one(
        "SELECT plan,billing_reference,plan_expires_at FROM users WHERE id=?", (user_id,)
    ))
    assert user and user["plan"] == "creator" and user["billing_reference"] == "sub_pause_resume"
    assert str(user["plan_expires_at"]).startswith("2026-09-01")

    resumed = {
        "event": "subscription.resumed",
        "created_at": 501,
        "payload": {"subscription": {"entity": entity(
            "sub_pause_resume", "plan_creator", status="active", start=END_EPOCH, end=NEXT_END_EPOCH
        )}},
    }
    response = _post_subscription_webhook(client, resumed, "evt_resume")
    assert response.status_code == 204
    user = asyncio.run(fetch_one(
        "SELECT plan,billing_reference,plan_started_at,plan_expires_at FROM users WHERE id=?", (user_id,)
    ))
    assert user and user["plan"] == "creator" and user["billing_reference"] == "sub_pause_resume"
    assert str(user["plan_started_at"]).startswith("2026-09-01")
    assert str(user["plan_expires_at"]).startswith("2026-10-01")


def test_pending_subscription_plan_id_does_not_apply_plan_change_before_active_provider_truth(client: TestClient):
    """A retry/pending state may expose a scheduled/new plan id before payment."""
    user_id = signup(client, "pending-plan-not-paid@example.com")
    asyncio.run(seed_plan_map())
    asyncio.run(make_recurring(user_id, "creator", "sub_pending_plan"))

    pending = {
        "event": "subscription.pending",
        "created_at": 600,
        "payload": {"subscription": {"entity": entity(
            "sub_pending_plan", "plan_growth", status="pending", start=START_EPOCH, end=END_EPOCH
        )}},
    }
    response = _post_subscription_webhook(client, pending, "evt_pending_plan_not_paid")
    assert response.status_code == 204
    user = asyncio.run(fetch_one(
        "SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)
    ))
    assert user and user["plan"] == "creator" and user["billing_reference"] == "sub_pending_plan"


def test_subscription_webhook_does_not_block_on_provider_followup_api(client: TestClient):
    """Webhook acknowledgement/reconciliation stays DB-local for scheduled changes."""
    user_id = signup(client, "webhook-no-provider-followup@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_webhook_fast"))
    payload = {
        "event": "subscription.updated",
        "created_at": 700,
        "payload": {"subscription": {"entity": entity(
            "sub_webhook_fast", "plan_creator", status="active", scheduled=True, scheduled_at=END_EPOCH
        )}},
    }
    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=AssertionError("webhook must not call Razorpay API"))):
        response = _post_subscription_webhook(client, payload, "evt_webhook_db_local")
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id=?", (user_id,)))
    assert user and user["plan"] == "creator" and user["billing_reference"] == "sub_webhook_fast"

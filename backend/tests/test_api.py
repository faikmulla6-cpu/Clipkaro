from unittest.mock import AsyncMock, patch
import asyncio
import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient
from app.core.config import get_settings
from app.core.database import UsageQuotaExceeded, execute, fetch_all, fetch_one
from app.main import app
from app.services.legal import LEGAL_VERSION


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
        "allow_live_razorpay_in_development": settings.allow_live_razorpay_in_development,
    }
    settings.database_path = tmp_path / "test.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = True
    settings.app_env = "test"
    settings.razorpay_mode = "test"
    settings.razorpay_key_id = "rzp_test_public"
    settings.razorpay_key_secret = "test-secret-for-signatures"
    settings.razorpay_webhook_secret = "webhook-test-secret"
    settings.allow_live_razorpay_in_development = False
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def login_demo(client: TestClient):
    response = client.post("/api/v1/auth/login", json={"email": "demo@clipkaro.ai", "password": "ClipKaro123!"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post("/api/v1/legal/accept", json={"accepted": True, "version": LEGAL_VERSION})
    assert accepted.status_code == 200


def test_authentication_and_usage(client: TestClient):
    assert client.get("/api/v1/auth/me").status_code == 401
    signup = client.post("/api/v1/auth/signup", json={"name": "Creator", "email": "creator@example.com", "password": "Secure123"})
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    assert signup.json()["user"]["plan"] == "free"
    assert client.get("/api/v1/usage").json()["exports_limit"] == 2
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/projects").status_code == 401


def test_owned_project_analysis_and_export_queue(client: TestClient):
    login_demo(client)
    with patch("app.api.routes._process_project", new=AsyncMock()):
        upload = client.post("/api/v1/projects/upload", data={"title": "Launch video"},
                             files={"file": ("launch.mp4", b"test-bytes", "video/mp4")})
    assert upload.status_code == 201
    project_id = upload.json()["id"]
    analysis = client.post(f"/api/v1/projects/{project_id}/analyse", json={"language": "en", "segments": [
        {"start": 0, "end": 12, "text": "Most creators make this mistake when they explain an idea."},
        {"start": 12, "end": 26, "text": "The secret is to promise one clear result and remove every distraction."},
        {"start": 26, "end": 42, "text": "Follow these three steps and your audience will understand the value immediately."},
    ]})
    assert analysis.status_code == 200 and analysis.json()
    clip = analysis.json()[0]
    assert clip["score_breakdown"]["hook"] > 0
    with patch("app.api.routes._render_export", new=AsyncMock()):
        export = client.post(f"/api/v1/clips/{clip['id']}/export", json={"resolution": "1080p", "watermark": False})
    assert export.status_code == 202
    assert export.json()["job_id"]


def test_project_ownership_is_enforced(client: TestClient):
    login_demo(client)
    with patch("app.api.routes._process_project", new=AsyncMock()):
        upload = client.post("/api/v1/projects/upload", data={"title": "Private"},
                             files={"file": ("private.mp4", b"private", "video/mp4")})
    project_id = upload.json()["id"]
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/signup", json={"name": "Other User", "email": "other@example.com", "password": "Secure123"})
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_signed_billing_webhook_is_idempotent(client: TestClient):
    settings = get_settings()
    settings.razorpay_webhook_secret = "webhook-test-secret"
    asyncio.run(execute(
        "INSERT OR REPLACE INTO billing_plans(plan_key,provider_plan_id,amount,currency,created_at) VALUES (?,?,?,?,?)",
        ("pro", "plan_pro", 79900, "INR", "2026-08-16T00:00:00+00:00"),
    ))
    asyncio.run(execute(
        "UPDATE users SET plan='free',billing_reference=NULL,plan_started_at=NULL,plan_expires_at=NULL WHERE id='demo-user'"
    ))
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
        ("checkout-sub-webhook", "demo-user", "subscription", "pro", "sub_webhook_test", 79900, "2026-08-16T00:00:00+00:00"),
    ))
    payload = {"event_id": "evt_test_1", "event": "subscription.activated", "payload": {
        "subscription": {"entity": {
            "id": "sub_webhook_test", "plan_id": "plan_pro", "status": "active", "paid_count": 1,
            "current_start": 1786838400, "current_end": 1789516800,
            # Notes are deliberately wrong; server-created checkout + provider plan id are authority.
            "notes": {"user_id": "attacker-controlled-note", "plan": "creator"},
        }},
        "payment": {"entity": {"id": "pay_sub_webhook", "status": "captured", "amount": 79900}},
    }}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json", "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": "evt_test_1",
    }
    first = client.post("/api/v1/billing/razorpay/webhook", content=raw, headers=headers)
    second = client.post("/api/v1/billing/razorpay/webhook", content=raw, headers=headers)
    assert first.status_code == second.status_code == 204
    login_demo(client)
    assert client.get("/api/v1/auth/me").json()["plan"] == "pro"
    checkout = asyncio.run(fetch_one("SELECT status,payment_id FROM billing_checkouts WHERE id='checkout-sub-webhook'"))
    assert checkout and checkout["status"] == "verified" and checkout["payment_id"] == "pay_sub_webhook"
    events = asyncio.run(fetch_all("SELECT * FROM payment_events WHERE provider_event_id='evt_test_1'"))
    assert len(events) == 1 and events[0]["status"] == "verified" and events[0]["plan"] == "pro"


def test_concurrent_webhook_processing_claim_is_retryable(client: TestClient):
    settings = get_settings()
    event_id = "evt_processing_duplicate"
    asyncio.run(execute(
        """INSERT INTO payment_events(
             id,provider_event_id,user_id,event_type,plan,amount,status,payload_json,created_at
           ) VALUES (?,?,NULL,?,NULL,0,'processing','{}',?)""",
        ("processing-claim", event_id, "payment.captured", __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()),
    ))
    payload = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_processing", "status": "captured"}}}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/billing/razorpay/webhook", content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
        },
    )
    assert response.status_code == 503
    claim = asyncio.run(fetch_one("SELECT status FROM payment_events WHERE provider_event_id=?", (event_id,)))
    assert claim and claim["status"] == "processing"


def test_stale_webhook_processing_claim_is_reclaimed(client: TestClient):
    settings = get_settings()
    event_id = "evt_stale_processing_claim"
    asyncio.run(execute(
        """INSERT INTO payment_events(
             id,provider_event_id,user_id,event_type,plan,amount,status,payload_json,created_at
           ) VALUES (?,?,NULL,?,NULL,0,'processing','{}',?)""",
        ("stale-processing-claim", event_id, "payment.captured", "2020-01-01T00:00:00+00:00"),
    ))
    payload = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_stale", "status": "captured"}}}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/billing/razorpay/webhook", content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
        },
    )
    assert response.status_code == 204
    claim = asyncio.run(fetch_one(
        "SELECT status,created_at FROM payment_events WHERE provider_event_id=?", (event_id,)
    ))
    assert claim and claim["status"] == "captured" and claim["created_at"] != "2020-01-01T00:00:00+00:00"


def test_failed_webhook_reconciliation_releases_processing_claim(client: TestClient):
    settings = get_settings()
    event_id = "evt_release_failed_claim"
    payload = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_release", "status": "captured"}}}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    with patch(
        "app.api.billing_lifecycle._complete_webhook_event",
        new=AsyncMock(side_effect=RuntimeError("synthetic persistence failure")),
    ):
        with pytest.raises(RuntimeError, match="synthetic persistence failure"):
            client.post(
                "/api/v1/billing/razorpay/webhook", content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": signature,
                    "X-Razorpay-Event-Id": event_id,
                },
            )
    claim = asyncio.run(fetch_one("SELECT id FROM payment_events WHERE provider_event_id=?", (event_id,)))
    assert claim is None


def test_subscription_webhook_notes_cannot_grant_entitlement_without_server_binding(client: TestClient):
    settings = get_settings()
    settings.razorpay_webhook_secret = "webhook-test-secret"
    payload = {"event": "subscription.activated", "payload": {
        "subscription": {"entity": {
            "id": "sub_unbound_notes_only", "plan_id": "plan_unknown", "status": "active", "paid_count": 1,
            "notes": {"user_id": "demo-user", "plan": "agency"},
        }}
    }}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/billing/razorpay/webhook", content=raw,
        headers={
            "Content-Type": "application/json", "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_unbound_notes_only",
        },
    )
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id='demo-user'"))
    assert user and user["plan"] == "creator" and not user["billing_reference"]
    event = asyncio.run(fetch_one(
        "SELECT user_id,plan FROM payment_events WHERE provider_event_id='evt_unbound_notes_only'"
    ))
    assert event and event["user_id"] is None and event["plan"] is None


def test_webhook_prefers_provider_event_header_and_redacts_payer_details(client: TestClient):
    settings = get_settings()
    settings.razorpay_webhook_secret = "webhook-test-secret"
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_private_payload",
                    "amount": 19900,
                    "status": "captured",
                    "email": "private@example.com",
                    "contact": "+919999999999",
                    "card": {"last4": "1111"},
                }
            }
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/billing/razorpay/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_header_authoritative",
        },
    )
    assert response.status_code == 204
    event = asyncio.run(fetch_one(
        "SELECT provider_event_id,payload_json FROM payment_events WHERE provider_event_id=?",
        ("evt_header_authoritative",),
    ))
    assert event and event["provider_event_id"] == "evt_header_authoritative"
    stored = json.loads(event["payload_json"])
    payment = stored["payload"]["payment"]["entity"]
    assert payment["email"] == "[redacted]"
    assert payment["contact"] == "[redacted]"
    assert payment["card"] == "[redacted]"



def test_one_time_payment_captured_webhook_recovers_lost_browser_callback(client: TestClient):
    settings = get_settings()
    settings.razorpay_webhook_secret = "webhook-test-secret"
    order_id = "order_mini_webhook_recovery"
    payment_id = "pay_mini_webhook_recovery"
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
        ("checkout-mini-webhook", "demo-user", "one_time", "mini_pass", order_id, 5900, "2026-08-16T00:00:00+00:00"),
    ))
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id, "order_id": order_id, "amount": 5900,
                    "currency": "INR", "status": "captured",
                }
            }
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": "evt_mini_webhook_recovery",
    }
    first = client.post("/api/v1/billing/razorpay/webhook", content=raw, headers=headers)
    second = client.post("/api/v1/billing/razorpay/webhook", content=raw, headers=headers)
    assert first.status_code == second.status_code == 204

    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id='demo-user'"))
    checkout = asyncio.run(fetch_one("SELECT status,payment_id FROM billing_checkouts WHERE id='checkout-mini-webhook'"))
    events = asyncio.run(fetch_all(
        "SELECT * FROM payment_events WHERE provider_event_id='evt_mini_webhook_recovery'"
    ))
    assert user and user["plan"] == "mini_pass" and user["billing_reference"] == order_id
    assert checkout and checkout["status"] == "verified" and checkout["payment_id"] == payment_id
    assert len(events) == 1 and events[0]["status"] == "verified"


def test_one_time_failed_then_late_authorized_webhooks_never_grant_before_capture(client: TestClient):
    settings = get_settings()
    order_id = "order_mini_late_authorization"
    payment_id = "pay_mini_late_authorization"
    asyncio.run(execute(
        "UPDATE users SET plan='free',billing_reference=NULL,plan_started_at=NULL,plan_expires_at=NULL WHERE id='demo-user'"
    ))
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
        ("checkout-mini-late-auth", "demo-user", "one_time", "mini_pass", order_id, 5900, "2026-08-16T00:00:00+00:00"),
    ))

    def deliver(event_id: str, event_type: str, status: str) -> None:
        payload = {
            "event": event_type,
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id, "order_id": order_id, "amount": 5900,
                        "currency": "INR", "status": status,
                    }
                }
            },
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        response = client.post(
            "/api/v1/billing/razorpay/webhook", content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": event_id,
            },
        )
        assert response.status_code == 204

    deliver("evt_mini_failed", "payment.failed", "failed")
    checkout = asyncio.run(fetch_one("SELECT status,payment_id FROM billing_checkouts WHERE id='checkout-mini-late-auth'"))
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id='demo-user'"))
    assert checkout and checkout["status"] == "failed" and checkout["payment_id"] == payment_id
    assert user and user["plan"] == "free" and not user["billing_reference"]

    # Razorpay documents that a payment can be authorised after first appearing
    # failed. That late state is recorded but still cannot grant entitlement.
    deliver("evt_mini_authorized", "payment.authorized", "authorized")
    checkout = asyncio.run(fetch_one("SELECT status FROM billing_checkouts WHERE id='checkout-mini-late-auth'"))
    user = asyncio.run(fetch_one("SELECT plan FROM users WHERE id='demo-user'"))
    assert checkout and checkout["status"] == "authorized"
    assert user and user["plan"] == "free"

    # Only captured provider truth is allowed to activate the Mini Pass.
    deliver("evt_mini_captured_after_auth", "payment.captured", "captured")
    checkout = asyncio.run(fetch_one("SELECT status FROM billing_checkouts WHERE id='checkout-mini-late-auth'"))
    user = asyncio.run(fetch_one("SELECT plan,billing_reference FROM users WHERE id='demo-user'"))
    assert checkout and checkout["status"] == "verified"
    assert user and user["plan"] == "mini_pass" and user["billing_reference"] == order_id


def test_one_time_webhook_never_activates_amount_mismatch(client: TestClient):
    settings = get_settings()
    settings.razorpay_webhook_secret = "webhook-test-secret"
    order_id = "order_mini_bad_amount"
    asyncio.run(execute(
        """INSERT INTO billing_checkouts(
             id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           ) VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
        ("checkout-mini-bad-amount", "demo-user", "one_time", "mini_pass", order_id, 5900, "2026-08-16T00:00:00+00:00"),
    ))
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_bad_amount", "order_id": order_id, "amount": 5800,
                    "currency": "INR", "status": "captured",
                }
            }
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/billing/razorpay/webhook", content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_mini_bad_amount",
        },
    )
    assert response.status_code == 204
    user = asyncio.run(fetch_one("SELECT plan FROM users WHERE id='demo-user'"))
    checkout = asyncio.run(fetch_one("SELECT status FROM billing_checkouts WHERE id='checkout-mini-bad-amount'"))
    event = asyncio.run(fetch_one(
        "SELECT status FROM payment_events WHERE provider_event_id='evt_mini_bad_amount'"
    ))
    # The mismatched payment must not change the account entitlement. The
    # seeded demo account starts on Creator, so it must remain Creator here.
    assert user and user["plan"] == "creator"
    assert checkout and checkout["status"] == "created"
    assert event and event["status"] == "rejected_amount_mismatch"

def test_locked_fair_access_plans(client: TestClient):
    rows = client.get("/api/v1/plans").json()
    by_id = {row["id"]: row for row in rows}
    assert by_id["free"]["price"] == 0 and by_id["free"]["processing_minutes"] == 15 and by_id["free"]["exports"] == 2
    assert by_id["mini_pass"]["price"] == 59 and by_id["mini_pass"]["processing_minutes"] == 25 and by_id["mini_pass"]["exports"] == 5
    assert by_id["creator"]["price"] == 199 and by_id["creator"]["processing_minutes"] == 60 and by_id["creator"]["exports"] == 15
    assert by_id["growth"]["price"] == 399 and by_id["growth"]["processing_minutes"] == 180 and by_id["growth"]["exports"] == 50
    assert by_id["pro"]["price"] == 799 and by_id["pro"]["processing_minutes"] == 480 and by_id["pro"]["exports"] == 150
    assert by_id["agency"]["price"] == 1999 and by_id["agency"]["processing_minutes"] == 1500 and by_id["agency"]["exports"] == 500



def test_duplicate_mini_pass_checkout_reuses_same_order(client: TestClient):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Retry Buyer", "email": "retry-mini@example.com", "password": "Secure123"},
    )
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post("/api/v1/legal/accept", json={"accepted": True, "version": LEGAL_VERSION})
    assert accepted.status_code == 200

    provider = AsyncMock(return_value={"id": "order_retry_same"})
    with patch("app.api.billing_lifecycle.razorpay_request", new=provider):
        first = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
        second = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})

    assert first.status_code == second.status_code == 200
    assert first.json()["order_id"] == second.json()["order_id"] == "order_retry_same"
    assert provider.await_count == 1
    rows = asyncio.run(fetch_all(
        "SELECT provider_reference,status FROM billing_checkouts WHERE user_id=? AND plan='mini_pass'",
        (signup.json()["user"]["id"],),
    ))
    assert len(rows) == 1 and rows[0]["provider_reference"] == "order_retry_same" and rows[0]["status"] == "created"


def test_duplicate_subscription_checkout_reuses_same_subscription(client: TestClient):
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Retry Subscriber", "email": "retry-sub@example.com", "password": "Secure123"},
    )
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post("/api/v1/legal/accept", json={"accepted": True, "version": LEGAL_VERSION})
    assert accepted.status_code == 200

    ensure_plan = AsyncMock(return_value="plan_growth_retry")
    provider = AsyncMock(return_value={"id": "sub_retry_same"})
    with patch("app.api.billing_lifecycle.ensure_razorpay_plan", new=ensure_plan), \
         patch("app.api.billing_lifecycle.razorpay_request", new=provider):
        first = client.post("/api/v1/billing/checkout", json={"plan": "growth"})
        second = client.post("/api/v1/billing/checkout", json={"plan": "growth"})

    assert first.status_code == second.status_code == 200
    assert first.json()["subscription_id"] == second.json()["subscription_id"] == "sub_retry_same"
    assert ensure_plan.await_count == 1
    assert provider.await_count == 1
    rows = asyncio.run(fetch_all(
        "SELECT provider_reference,status FROM billing_checkouts WHERE user_id=? AND plan='growth'",
        (signup.json()["user"]["id"],),
    ))
    assert len(rows) == 1 and rows[0]["provider_reference"] == "sub_retry_same" and rows[0]["status"] == "created"


def test_mini_pass_order_is_verified_before_entitlement(client: TestClient):
    login_demo(client)
    settings = get_settings()
    settings.razorpay_key_id = "rzp_test_public"
    settings.razorpay_key_secret = "test-secret-for-signatures"
    payment_id = "pay_mini_success"

    async def mini_provider(method, path, **kwargs):
        if method == "POST" and path == "/orders":
            return {"id": "order_clipkaro_mini"}
        if method == "GET" and path == f"/payments/{payment_id}":
            return {
                "id": payment_id, "order_id": "order_clipkaro_mini",
                "amount": 5900, "currency": "INR", "status": "captured", "captured": True,
            }
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=mini_provider)):
        checkout = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
        assert checkout.status_code == 200
        assert checkout.json()["kind"] == "one_time"
        signature = hmac.new(settings.razorpay_key_secret.encode(), f"order_clipkaro_mini|{payment_id}".encode(), hashlib.sha256).hexdigest()
        verified = client.post("/api/v1/billing/verify", json={
            "razorpay_order_id": "order_clipkaro_mini",
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
    assert verified.status_code == 200 and verified.json()["activated"] is True
    assert client.get("/api/v1/auth/me").json()["plan"] == "mini_pass"
    usage = client.get("/api/v1/usage").json()
    assert usage["exports_limit"] == 5
    assert usage["processing_minutes_limit"] == 25


def test_mini_pass_authorized_but_uncaptured_payment_does_not_activate(client: TestClient):
    login_demo(client)
    settings = get_settings()
    settings.razorpay_mode = "test"
    settings.razorpay_key_id = "rzp_test_public"
    settings.razorpay_key_secret = "test-secret-for-signatures"
    payment_id = "pay_mini_authorized"

    async def provider(method, path, **kwargs):
        if method == "POST" and path == "/orders":
            return {"id": "order_clipkaro_authorized"}
        if method == "GET" and path == f"/payments/{payment_id}":
            return {
                "id": payment_id, "order_id": "order_clipkaro_authorized",
                "amount": 5900, "currency": "INR", "status": "authorized", "captured": False,
            }
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)):
        checkout = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
        assert checkout.status_code == 200
        signature = hmac.new(
            settings.razorpay_key_secret.encode(),
            f"order_clipkaro_authorized|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        verified = client.post("/api/v1/billing/verify", json={
            "razorpay_order_id": "order_clipkaro_authorized",
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })

    assert verified.status_code == 200
    assert verified.json() == {"verified": True, "activated": False, "plan": "mini_pass"}
    assert client.get("/api/v1/auth/me").json()["plan"] == "creator"
    checkout_row = asyncio.run(fetch_one(
        "SELECT status,payment_id FROM billing_checkouts WHERE provider_reference=?",
        ("order_clipkaro_authorized",),
    ))
    assert checkout_row and checkout_row["status"] == "authorized"
    assert checkout_row["payment_id"] == payment_id


def test_mini_pass_browser_callback_rejects_provider_amount_mismatch(client: TestClient):
    login_demo(client)
    settings = get_settings()
    settings.razorpay_mode = "test"
    settings.razorpay_key_id = "rzp_test_public"
    settings.razorpay_key_secret = "test-secret-for-signatures"
    payment_id = "pay_mini_bad_provider_amount"

    async def provider(method, path, **kwargs):
        if method == "POST" and path == "/orders":
            return {"id": "order_clipkaro_bad_provider_amount"}
        if method == "GET" and path == f"/payments/{payment_id}":
            return {
                "id": payment_id, "order_id": "order_clipkaro_bad_provider_amount",
                "amount": 1, "currency": "INR", "status": "captured", "captured": True,
            }
        raise AssertionError((method, path, kwargs))

    with patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)):
        checkout = client.post("/api/v1/billing/checkout", json={"plan": "mini_pass"})
        assert checkout.status_code == 200
        signature = hmac.new(
            settings.razorpay_key_secret.encode(),
            f"order_clipkaro_bad_provider_amount|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        verified = client.post("/api/v1/billing/verify", json={
            "razorpay_order_id": "order_clipkaro_bad_provider_amount",
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })

    assert verified.status_code == 400
    assert client.get("/api/v1/auth/me").json()["plan"] == "creator"
    checkout_row = asyncio.run(fetch_one(
        "SELECT status FROM billing_checkouts WHERE provider_reference=?",
        ("order_clipkaro_bad_provider_amount",),
    ))
    assert checkout_row and checkout_row["status"] == "created"


def test_growth_subscription_signature_and_provider_plan_are_verified(client: TestClient):
    client.post("/api/v1/auth/signup", json={"name": "Growth Creator", "email": "growth@example.com", "password": "Secure123"})
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post("/api/v1/legal/accept", json={"accepted": True, "version": LEGAL_VERSION})
    assert accepted.status_code == 200
    settings = get_settings()
    settings.razorpay_key_id = "rzp_test_public"
    settings.razorpay_key_secret = "test-secret-for-signatures"

    async def provider(method, path, **kwargs):
        if method == "POST" and path == "/subscriptions":
            return {"id": "sub_growth_success"}
        if method == "GET" and path == "/subscriptions/sub_growth_success":
            return {
                "id": "sub_growth_success", "plan_id": "plan_growth_live", "status": "active", "paid_count": 1,
                "current_start": 1786089600, "current_end": 1788768000,
            }
        raise AssertionError((method, path, kwargs))

    async def ensure_growth_plan(_plan):
        await execute(
            "INSERT OR REPLACE INTO billing_plans(plan_key,provider_plan_id,amount,currency,created_at) VALUES (?,?,?,?,?)",
            ("growth", "plan_growth_live", 39900, "INR", "2026-08-07T00:00:00+00:00"),
        )
        return "plan_growth_live"

    with patch("app.api.billing_lifecycle.ensure_razorpay_plan", new=AsyncMock(side_effect=ensure_growth_plan)), \
         patch("app.api.billing_lifecycle.razorpay_request", new=AsyncMock(side_effect=provider)):
        checkout = client.post("/api/v1/billing/checkout", json={"plan": "growth"})
        assert checkout.status_code == 200 and checkout.json()["subscription_id"] == "sub_growth_success"
        payment_id = "pay_growth_success"
        signature = hmac.new(settings.razorpay_key_secret.encode(), f"{payment_id}|sub_growth_success".encode(), hashlib.sha256).hexdigest()
        verified = client.post("/api/v1/billing/verify", json={
            "razorpay_subscription_id": "sub_growth_success",
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
    assert verified.status_code == 200 and verified.json()["activated"] is True
    assert client.get("/api/v1/auth/me").json()["plan"] == "growth"
    usage = client.get("/api/v1/usage").json()
    assert usage["exports_limit"] == 50
    assert usage["processing_minutes_limit"] == 180


def test_karo_minutes_are_atomically_reserved_and_refunded(client: TestClient):
    signup = client.post("/api/v1/auth/signup", json={
        "name": "Race Creator", "email": "race-minutes@example.com", "password": "Secure123"
    })
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    with patch("app.api.routes._process_project", new=AsyncMock()):
        first = client.post("/api/v1/projects/upload", data={"title": "First"},
                            files={"file": ("first.mp4", b"first", "video/mp4")}).json()
        second = client.post("/api/v1/projects/upload", data={"title": "Second"},
                             files={"file": ("second.mp4", b"second", "video/mp4")}).json()

    async def compete():
        async def validate(video_id: str) -> bool:
            try:
                await execute("UPDATE videos SET duration=?,width=?,height=?,status='validated' WHERE id=?",
                              (600.0, 1920, 1080, video_id))
                return True
            except UsageQuotaExceeded:
                return False
        return await asyncio.gather(validate(first["video_id"]), validate(second["video_id"]))

    results = asyncio.run(compete())
    assert sum(bool(value) for value in results) == 1
    usage = client.get("/api/v1/usage").json()
    assert usage["source_minutes"] == 10.0
    assert usage["processing_minutes_remaining"] == 5.0
    reservations = asyncio.run(fetch_all(
        "SELECT * FROM usage_reservations WHERE kind='minutes' ORDER BY created_at"
    ))
    assert len(reservations) == 1 and reservations[0]["status"] == "reserved"

    winner_project = first["id"] if results[0] else second["id"]
    loser_video = second["video_id"] if results[0] else first["video_id"]
    loser_project = second["id"] if results[0] else first["id"]
    asyncio.run(execute("UPDATE projects SET status='failed' WHERE id=?", (winner_project,)))
    assert client.get("/api/v1/usage").json()["source_minutes"] == 0.0

    asyncio.run(execute("UPDATE videos SET duration=?,width=?,height=?,status='validated' WHERE id=?",
                        (600.0, 1920, 1080, loser_video)))
    assert client.get("/api/v1/usage").json()["source_minutes"] == 10.0
    asyncio.run(execute("UPDATE projects SET status='ready' WHERE id=?", (loser_project,)))
    final = asyncio.run(fetch_all(
        "SELECT status FROM usage_reservations WHERE kind='minutes' ORDER BY created_at"
    ))
    assert [row["status"] for row in final] == ["released", "finalized"]
    assert client.get("/api/v1/usage").json()["source_minutes"] == 10.0


def test_export_slots_are_atomically_reserved_and_refunded(client: TestClient):
    signup = client.post("/api/v1/auth/signup", json={
        "name": "Export Racer", "email": "race-exports@example.com", "password": "Secure123"
    })
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    user_id = signup.json()["user"]["id"]
    with patch("app.api.routes._process_project", new=AsyncMock()):
        upload = client.post("/api/v1/projects/upload", data={"title": "Export race"},
                             files={"file": ("race.mp4", b"race", "video/mp4")}).json()
    analysis = client.post(f"/api/v1/projects/{upload['id']}/analyse", json={"language": "en", "segments": [
        {"start": 0, "end": 12, "text": "Why do most creators lose attention before the useful part begins?"},
        {"start": 12, "end": 27, "text": "The answer is simple: make the result clear before you explain the process."},
        {"start": 27, "end": 44, "text": "That single change gives the viewer a reason to stay until the end."},
    ]})
    assert analysis.status_code == 200 and analysis.json()
    clip_id = analysis.json()[0]["id"]
    client.get("/api/v1/usage")
    usage_row = asyncio.run(fetch_one("SELECT * FROM usage WHERE user_id=?", (user_id,)))
    assert usage_row
    asyncio.run(execute("UPDATE usage SET exports_used=1 WHERE id=?", (usage_row["id"],)))

    created = "2026-08-07T00:00:00+00:00"
    expires = "2026-08-08T00:00:00+00:00"
    export_ids = ["race-export-a", "race-export-b"]

    async def compete():
        async def reserve(export_id: str) -> bool:
            try:
                await execute(
                    "INSERT INTO exports VALUES (?, ?, ?, ?, '720p', '9:16', 'clean', 1, 'queued', 0, NULL, ?, ?)",
                    (export_id, clip_id, user_id, f"/tmp/{export_id}.mp4", created, expires),
                )
                return True
            except UsageQuotaExceeded:
                return False
        return await asyncio.gather(*(reserve(export_id) for export_id in export_ids))

    results = asyncio.run(compete())
    assert sum(bool(value) for value in results) == 1
    usage = client.get("/api/v1/usage").json()
    assert usage["exports_used"] == 2 and usage["exports_remaining"] == 0
    reservations = asyncio.run(fetch_all(
        "SELECT * FROM usage_reservations WHERE kind='export' ORDER BY created_at"
    ))
    assert len(reservations) == 1 and reservations[0]["status"] == "reserved"

    winner_id = export_ids[0] if results[0] else export_ids[1]
    asyncio.run(execute("UPDATE exports SET status='failed' WHERE id=?", (winner_id,)))
    usage = client.get("/api/v1/usage").json()
    assert usage["exports_used"] == 1 and usage["exports_remaining"] == 1

    retry_id = "race-export-retry"
    asyncio.run(execute(
        "INSERT INTO exports VALUES (?, ?, ?, ?, '720p', '9:16', 'clean', 1, 'queued', 0, NULL, ?, ?)",
        (retry_id, clip_id, user_id, f"/tmp/{retry_id}.mp4", created, expires),
    ))
    asyncio.run(execute("UPDATE exports SET status='ready' WHERE id=?", (retry_id,)))
    usage = client.get("/api/v1/usage").json()
    assert usage["exports_used"] == 2 and usage["exports_remaining"] == 0
    statuses = asyncio.run(fetch_all(
        "SELECT resource_id,status FROM usage_reservations WHERE kind='export' ORDER BY created_at"
    ))
    assert [row["status"] for row in statuses] == ["released", "finalized"]

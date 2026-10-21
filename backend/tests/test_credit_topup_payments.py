"""Server-priced allowance purchase and exact-once payment tests."""
import asyncio
import hashlib
import hmac
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from app.api import credit_topups as topups
from test_real_minutes_finished_shorts import buy,client

def run(coro): return asyncio.run(coro)

@pytest.mark.parametrize("minutes,shorts,price", [(10,0,3000),(0,1,200),(10,2,3400),(120,15,39000)])
def test_authoritative_price(minutes,shorts,price):
    assert topups.validate_quantities("creator",minutes,shorts)[2]==price

@pytest.mark.parametrize("minutes,shorts",[(9,0),(-1,1),(121,0),(0,16),(0,0),(True,0),("10",0),(1.5,1)])
def test_untrusted_quantities_rejected(minutes,shorts):
    with pytest.raises(HTTPException):topups.validate_quantities("creator",minutes,shorts)

def test_capture_identity():
    order={"provider_reference":"order_fake","amount_paise":3400}
    p={"id":"pay_fake","order_id":"order_fake","amount":3400,"currency":"INR","status":"captured","captured":True}
    assert topups.payment_matches(p,order,"pay_fake")==(True,True)
    for k,v in (("amount",3399),("currency","USD"),("order_id","order_wrong"),("status","authorized")):
        assert not topups.payment_matches({**p,k:v},order,"pay_fake")[1]

def test_checkout_credits_once_despite_browser_and_webhook_retries(client):
    uid=buy(client,"creator","topup-checkout@example.com")
    order={"id":"order_test_credits_314"}
    p={"id":"pay_test_314","order_id":order["id"],"amount":3400,"currency":"INR","status":"captured","captured":True}
    async def provider(method,path,**kwargs):
        if method=="POST" and path=="/orders":
            assert kwargs["json_body"]["amount"]==3400
            return order
        if method=="GET" and path=="/payments/pay_test_314":return p
        raise AssertionError((method,path))
    with patch("app.api.credit_topups.razorpay_request",new=AsyncMock(side_effect=provider)):
        co=client.post("/api/v1/credits/checkout",json={"minutes":10,"shorts":2})
        assert co.status_code==200,co.text
        assert co.json()["amount"]==3400
        assert run(topups.balance_for(uid))==(0.0,0)
        bad=client.post("/api/v1/credits/verify",json={"razorpay_order_id":order["id"],"razorpay_payment_id":p["id"],"razorpay_signature":"forged"})
        assert bad.status_code==400 and run(topups.balance_for(uid))==(0.0,0)
        sig=hmac.new(topups.get_settings().razorpay_key_secret.encode(),f"{order['id']}|{p['id']}".encode(),hashlib.sha256).hexdigest()
        payload={"razorpay_order_id":order["id"],"razorpay_payment_id":p["id"],"razorpay_signature":sig}
        ok=client.post("/api/v1/credits/verify",json=payload)
        assert ok.status_code==200,ok.text
        assert ok.json()["verified"] is True
        assert run(topups.balance_for(uid))==(10.0,2)
        assert run(topups.reconcile_credit_topup_webhook("payment.captured",p,{}))["status"]=="verified"
        assert run(topups.reconcile_credit_topup_webhook("order.paid",p,{"id":order["id"],"status":"paid","amount_paid":3400,"currency":"INR"}))["status"]=="verified"
        assert client.post("/api/v1/credits/verify",json=payload).status_code==200
        assert run(topups.balance_for(uid))==(10.0,2)
        assert run(topups.reconcile_credit_topup_webhook("payment.captured",{**p,"amount":9999},{}))["status"]=="ignored"
        assert run(topups.balance_for(uid))==(10.0,2)

def test_missing_legal_acceptance_blocks_topup_before_razorpay(client):
    uid = buy(client, "creator", "unaccepted-topup@example.com")
    run(topups.execute("DELETE FROM legal_acceptances WHERE user_id=?", (uid,)))
    # An existing subscription is not consent for a new credit purchase.
    with patch("app.api.credit_topups.razorpay_request", new_callable=AsyncMock) as provider:
        response = client.post("/api/v1/credits/checkout", json={"minutes": 10, "shorts": 0})
    assert response.status_code == 403, response.text
    assert "Terms" in response.json()["detail"]
    provider.assert_not_awaited()
    assert run(topups.fetch_one("SELECT id FROM credit_topup_checkouts WHERE user_id=?", (uid,))) is None


# Wallet accounting must be tested separately from payment callbacks. These
# tests protect user balances through success, quota rejection and failure.
from app.core.database import execute, fetch_one, UsageQuotaExceeded
from test_real_minutes_finished_shorts import source, clip, export, usage

def _seed_wallet(user_id, minutes=0, shorts=0):
    run(execute(
        "INSERT INTO credit_topup_wallets(user_id,minutes_balance,shorts_balance,updated_at) VALUES (?,?,?,?)",
        (user_id, minutes, shorts, "2026-10-21T00:00:00Z"),
    ))

def test_paid_extra_minutes_only_spent_above_base_and_refunded_on_failure(client):
    uid=buy(client, "creator", "extra-minute-reserve@example.com")
    _seed_wallet(uid, minutes=10)
    source(uid,"base60a",60)
    source(uid,"base60b",60)
    assert run(topups.balance_for(uid))==(10.0,0)
    source(uid,"extra6",6,validated=False)
    run(execute("UPDATE videos SET duration=360,width=1280,height=720,status='validated' WHERE id='video-extra6'"))
    assert run(topups.balance_for(uid))==(4.0,0)
    reserved=run(fetch_one("SELECT amount,status FROM credit_topup_spends WHERE kind='minutes' AND resource_id='proj-extra6'"))
    assert reserved["amount"]==pytest.approx(6) and reserved["status"]=="reserved"
    run(execute("UPDATE projects SET status='failed' WHERE id='proj-extra6'"))
    assert run(topups.balance_for(uid))==(10.0,0)
    assert usage(client)["source_minutes"]==pytest.approx(120)
    source(uid,"success8",8)
    assert run(topups.balance_for(uid))==(2.0,0)
    assert run(fetch_one("SELECT status FROM credit_topup_spends WHERE kind='minutes' AND resource_id='proj-success8'"))["status"]=="finalized"
    with pytest.raises(UsageQuotaExceeded,match="Karo Minutes"):
        source(uid,"exceed3",3)
    assert run(topups.balance_for(uid))==(2.0,0)

def test_extra_short_first_finished_only_and_failed_render_refunded(client):
    uid=buy(client,"creator","extra-short-reserve@example.com")
    _seed_wallet(uid,shorts=2)
    video=source(uid,"short_base",5)
    for i in range(15):
        c=clip(video,f"short-base-{i}")
        export(uid,c,f"original-{i}","ready")
    assert run(topups.balance_for(uid))==(0.0,2)
    c=clip(video,"short-paid-1")
    export(uid,c,"paid-1")
    assert run(topups.balance_for(uid))==(0.0,1)
    run(execute("UPDATE exports SET status='failed' WHERE id='paid-1'"))
    assert run(topups.balance_for(uid))==(0.0,2)
    export(uid,c,"paid-1-retry","ready")
    assert run(topups.balance_for(uid))==(0.0,1)
    export(uid,c,"paid-1-reexport","ready")
    assert run(topups.balance_for(uid))==(0.0,1)
    c2=clip(video,"short-paid-2")
    export(uid,c2,"paid-2","ready")
    assert run(topups.balance_for(uid))==(0.0,0)
    c3=clip(video,"short-paid-3")
    with pytest.raises(UsageQuotaExceeded,match="Short"):
        export(uid,c3,"should-fail")

def test_legacy_topup_shorts_mean_source_project_slots(client):
    uid=buy(client,"creator","extra-legacy-source@example.com")
    user=run(fetch_one("SELECT * FROM users WHERE id=?",(uid,)))
    from app.services.billing import usage_period_key
    run(execute("UPDATE plan_entitlement_snapshots SET short_mode='source_projects', processing_minutes=60 WHERE user_id=? AND period_key=?",(uid,usage_period_key(user))))
    _seed_wallet(uid,minutes=10,shorts=1)
    for i in range(15):
        source(uid,f"legacy-project-{i}",0.1)
    assert usage(client)["shorts_remaining"]==1
    source(uid,"legacy-extra-1",0.1)
    assert run(topups.balance_for(uid))[1]==0
    with pytest.raises(UsageQuotaExceeded,match="Short"):
        source(uid,"legacy-extra-2",0.1)

"""Purchase-safe Karo Minutes and first-successful-finished-Short accounting.

All tests run against isolated SQLite and never call payment providers.
"""
import asyncio
from pathlib import Path

import pytest

from app.core.database import UsageQuotaExceeded, execute, fetch_one, fetch_all
from app.services.billing import PLAN_CATALOG, activate_entitlement, entitlement_for, usage_period_key
from test_subscription_lifecycle import client, fixed_billing_clock, signup, START, END


def run(operation):
    return asyncio.run(operation)


def buy(client, plan: str, email: str):
    user_id = signup(client, email)
    run(activate_entitlement(
        user_id, plan, f"sub_new_{user_id}" if plan != "mini_pass" else f"order_new_{user_id}",
        period_start=START, period_end=END,
    ))
    user = run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    rights = run(entitlement_for(user))
    assert rights["short_mode"] == "finished_shorts"
    assert rights["processing_minutes"] == PLAN_CATALOG[plan]["processing_minutes"]
    assert rights["price_paise"] == PLAN_CATALOG[plan]["price_paise"]
    return user_id


def source(user_id: str, key: str, source_minutes: float, *, validated=True):
    run(execute(
        "INSERT INTO projects(id,user_id,title,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
        (f"proj-{key}", user_id, key, "processing", START, START),
    ))
    run(execute(
        """INSERT INTO videos
           (id,project_id,original_filename,duration,width,height,file_size,file_path,status,created_at,expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (f"video-{key}", f"proj-{key}", f"{key}.mp4", 0, 0, 0,
         100, f"/tmp/{key}.mp4", "uploaded", START, END),
    ))
    if validated:
        run(execute(
            "UPDATE videos SET duration=?,width=1280,height=720,status='validated' WHERE id=?",
            (source_minutes * 60.0, f"video-{key}"),
        ))
        run(execute("UPDATE projects SET status='ready' WHERE id=?", (f"proj-{key}",)))
    return f"video-{key}"


def clip(video_id, key):
    run(execute(
        """INSERT INTO clips(id,video_id,start_time,end_time,hook,title,reason,transcript_text,
           score,score_breakdown_json,platform,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"clip-{key}", video_id, 0, 6, "hook", "title", "reason", "text",
         0.9, "{}", "youtube", "suggested", START, START),
    ))
    return f"clip-{key}"


def export(user_id, clip_id, key, status="queued"):
    run(execute(
        """INSERT INTO exports
           (id,clip_id,user_id,output_path,resolution,aspect_ratio,caption_style,watermark,
            status,progress,error,created_at,expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,0,NULL,?,?)""",
        (key, clip_id, user_id, f"/tmp/{key}.mp4", "1080p", "9:16", "clean", 0, "queued", START, END),
    ))
    if status != "queued":
        run(execute("UPDATE exports SET status=? WHERE id=?", (status, key)))


def usage(client):
    response=client.get("/api/v1/usage")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("plan,minutes,max_video,shorts,price", [
    ("mini_pass",25,25,5,59),
    ("creator",120,60,15,249),
    ("growth",300,90,50,599),
    ("pro",600,180,150,1299),
])
def test_new_entitlements_are_exact_and_deduct_finished_outputs(client,plan,minutes,max_video,shorts,price):
    user_id=buy(client,plan,f"accurate-{plan}@example.com")
    before=usage(client)
    assert (before["processing_minutes_limit"],before["source_video_limit_minutes"],
            before["shorts_limit"], before["plan_price_paise"]) == (minutes,max_video,shorts,price*100)
    assert before["short_unit"]=="finished_shorts"
    video=source(user_id,f"{plan}-a",5)
    assert usage(client)["source_minutes"]==5
    assert usage(client)["shorts_used"]==0  # source analysis produces candidates, not finished Shorts
    one=clip(video,f"{plan}-a1")
    export(user_id,one,f"{plan}-first")
    assert usage(client)["shorts_used"]==1
    with pytest.raises(UsageQuotaExceeded,match="already rendering"):
        export(user_id,one,f"{plan}-simultaneous")
    run(execute("UPDATE exports SET status='failed' WHERE id=?", (f"{plan}-first",)))
    assert usage(client)["shorts_used"]==0
    export(user_id,one,f"{plan}-retry","ready")
    assert usage(client)["shorts_used"]==1
    export(user_id,one,f"{plan}-rerender","ready")
    assert usage(client)["shorts_used"]==1
    second=clip(video,f"{plan}-a2")
    export(user_id,second,f"{plan}-second","ready")
    assert usage(client)["shorts_used"]==2
    assert usage(client)["source_minutes"]==5


def test_source_minutes_are_atomic_and_refunded_on_failure(client):
    user_id=buy(client,"creator","quota-new@example.com")
    source(user_id,"s60",60)
    source(user_id,"s59",59)
    assert usage(client)["processing_minutes_remaining"]==1.0
    with pytest.raises(UsageQuotaExceeded,match="Karo Minutes"):
        source(user_id,"s2",2)
    assert usage(client)["source_minutes"]==119.0
    run(execute("UPDATE projects SET status='failed' WHERE id='proj-s59'"))
    assert usage(client)["source_minutes"]==119.0, "Finalized project minutes are not refunded after a later failure"


def test_inflight_failed_processing_refunds_exact_source_minutes(client):
    user_id=buy(client,"creator","refund-source-new@example.com")
    source(user_id,"fail10",10,validated=False)
    run(execute("UPDATE videos SET duration=600,width=1280,height=720,status='validated' WHERE id='video-fail10'"))
    assert usage(client)["source_minutes"]==10
    run(execute("UPDATE projects SET status='failed' WHERE id='proj-fail10'"))
    assert usage(client)["source_minutes"]==0
    row=run(fetch_one("SELECT status FROM usage_reservations WHERE resource_id='proj-fail10'"))
    assert row["status"]=="released"


def test_existing_pass_keeps_original_125_minutes_and_source_credit_rules(client):
    user_id=signup(client,"legacy-pass-current@example.com")
    run(execute("UPDATE users SET plan='mini_pass',billing_reference='old_paid_order',plan_started_at=?,plan_expires_at=? WHERE id=?",
                (START,END,user_id)))
    user=run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    # Snapshot historical entitlement as migration would do for an existing purchaser.
    period=usage_period_key(user)
    run(execute("""INSERT INTO plan_entitlement_snapshots
       (user_id,period_key,plan_key,processing_minutes,shorts,source_video_limit_minutes,
        short_mode,price_paise,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
       (user_id,period,"mini_pass",125.0,5,25.0,"source_projects",5900,START)))
    assert usage(client)["processing_minutes_limit"]==125
    source(user_id,"oldvideo",20)
    assert usage(client)["shorts_used"]==1
    assert usage(client)["source_minutes"]==20


def test_paid_short_limit_blocks_new_clip_not_reexport(client):
    user_id=buy(client,"mini_pass","cap-new-pass@example.com")
    video=source(user_id,"short-source",5)
    ids=[]
    for i in range(5):
        c=clip(video,str(i))
        export(user_id,c,f"made-{i}","ready")
        ids.append(c)
    assert usage(client)["shorts_remaining"]==0
    export(user_id,ids[0],"free-existing-rerender","ready")
    assert usage(client)["shorts_used"]==5
    different=clip(video,"over")
    with pytest.raises(UsageQuotaExceeded,match="Short"):
        export(user_id,different,"blocked-sixth")


def test_checkout_rejects_stale_display_price_without_payment(client):
    from app.services.legal import LEGAL_VERSION
    user_id=signup(client,"stale-price-new@example.com")
    response=client.post("/api/v1/billing/checkout",json={
        "plan":"creator","expected_price_paise":19900
    })
    assert response.status_code==409
    assert "Refresh" in response.json()["detail"]
    assert run(fetch_one("SELECT id FROM billing_checkouts WHERE user_id=?", (user_id,))) is None


def test_legacy_subscription_snapshots_preserve_old_price_and_minutes(client):
    user_id=signup(client,"legacy-price-protected@example.com")
    reference="sub_existing_old_paid"
    run(execute("UPDATE users SET plan='creator',billing_reference=?,plan_started_at=?,plan_expires_at=? WHERE id=?",
                (reference,START,END,user_id)))
    run(execute("INSERT INTO legacy_billing_subscriptions(subscription_id,plan_key) VALUES (?,?)",
                (reference,"creator")))
    old=run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    rights=run(entitlement_for(old))
    assert rights["price_paise"]==19900
    assert rights["processing_minutes"]==60.0
    assert rights["short_mode"]=="source_projects"
    assert rights["source_video_limit_minutes"]==60
    assert usage(client)["processing_minutes_limit"]==60
    assert usage(client)["plan_price_paise"]==19900


def test_pre_cutover_pending_mini_pass_is_not_silently_downgraded(client):
    from app.api.billing_lifecycle import _activate_one_time_checkout
    user_id = signup(client, "captured-after-cutover@example.com")
    old = {
        "id": "legacy-checkout-100",
        "user_id": user_id,
        "kind": "one_time",
        "plan": "mini_pass",
        "provider_reference": "order_legacy_pending",
        "amount": 5900,
        "status": "authorized",
    }
    run(execute(
        """INSERT INTO billing_checkouts
           (id,user_id,kind,plan,provider_reference,amount,status,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (old["id"], user_id, "one_time", "mini_pass",
         old["provider_reference"], 5900, "authorized", START),
    ))
    run(execute(
        """INSERT INTO checkout_entitlement_snapshots
           (checkout_id,processing_minutes,shorts,source_video_limit_minutes,
            short_mode,price_paise,created_at) VALUES (?,?,?,?,?,?,?)""",
        (old["id"], 125, 5, 25, "source_projects", 5900, START),
    ))
    assert run(_activate_one_time_checkout(old, payment_id="pay_original")) is True
    assert run(_activate_one_time_checkout(old, payment_id="pay_original")) is False
    rights=usage(client)
    assert rights["processing_minutes_limit"] == 125
    assert rights["short_unit"] == "source_projects"
    assert rights["plan_price_paise"] == 5900
    assert rights["source_video_limit_minutes"] == 25


def test_new_pass_purchased_rights_are_not_overwritten_by_catalog(client):
    user_id=signup(client,"new-checkout-snapshot@example.com")
    from unittest.mock import AsyncMock, patch
    from app.services.legal import LEGAL_VERSION
    result = client.post("/api/v1/legal/accept",json={
        "accepted":True,"version":LEGAL_VERSION
    })
    assert result.status_code==200
    with patch("app.api.billing_lifecycle.razorpay_request",
               new=AsyncMock(return_value={"id":"order_snap_new"})):
        checkout=client.post("/api/v1/billing/checkout",json={
            "plan":"mini_pass","expected_price_paise":5900
        })
    assert checkout.status_code==200,checkout.text
    bought=run(fetch_one(
        """SELECT s.* FROM checkout_entitlement_snapshots s
           JOIN billing_checkouts c ON c.id=s.checkout_id
           WHERE c.user_id=? AND c.provider_reference=?""",
        (user_id, "order_snap_new"),
    ))
    assert bought and bought["processing_minutes"]==25
    assert bought["short_mode"]=="finished_shorts"
    assert bought["price_paise"]==5900

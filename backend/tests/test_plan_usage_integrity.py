"""Cross-plan entitlement and quota regressions. No real payments or accounts."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.api.billing_lifecycle import _apply_provider_entity
from app.core.database import execute, fetch_one
from app.services.billing import PLAN_CATALOG, usage_period_key

# Reuse the existing isolated SQLite/TestClient fixtures; all writes are test-only.
from test_subscription_lifecycle import (
    client, entity, fixed_billing_clock, make_recurring, seed_plan_map, signup,
    START, END, START_EPOCH, END_EPOCH, NEXT_END_EPOCH,
)


@pytest.mark.parametrize("previous_plan", ["free", "mini_pass"])
@pytest.mark.parametrize("paid_plan", ["creator", "growth", "pro", "agency"])
def test_first_paid_subscription_never_inherits_prior_usage(client, previous_plan, paid_plan):
    user_id = signup(client, f"fresh-{previous_plan}-{paid_plan}@example.com")
    asyncio.run(seed_plan_map())
    if previous_plan == "mini_pass":
        asyncio.run(execute(
            """UPDATE users SET plan='mini_pass',billing_reference='order_old',
               plan_started_at=?,plan_expires_at=? WHERE id=?""",
            (START, END, user_id),
        ))
    original = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    prior_period = usage_period_key(original)
    asyncio.run(execute(
        "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?,?,?,?,?,?)",
        (f"usage-{previous_plan}-{paid_plan}", user_id, prior_period, 12.34, 1, 5),
    ))
    asyncio.run(execute(
        """INSERT INTO usage_reservations(id,user_id,period_key,kind,amount,resource_id,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (f"reservation-{previous_plan}-{paid_plan}", user_id, prior_period, "minutes",
         12.34, "previous-video", "finalized", START, START),
    ))
    subscription = f"sub_new_{paid_plan}_{previous_plan}"
    with patch("app.api.billing_lifecycle._provider_scheduled_target", return_value=(None, None)):
        applied = asyncio.run(_apply_provider_entity(
            original, entity(subscription, f"plan_{paid_plan}"), allow_provider_followup=False,
        ))
    assert applied["plan"] == paid_plan
    current = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    period = usage_period_key(current)
    assert period != prior_period
    assert asyncio.run(fetch_one(
        "SELECT source_minutes FROM usage WHERE user_id=? AND month=?",
        (user_id, prior_period),
    ))["source_minutes"] == 12.34
    assert asyncio.run(fetch_one(
        "SELECT period_key FROM usage_reservations WHERE user_id=? AND resource_id='previous-video'",
        (user_id,),
    ))["period_key"] == prior_period
    usage = client.get("/api/v1/usage").json()
    assert usage["plan"] == paid_plan
    assert usage["processing_minutes_limit"] == PLAN_CATALOG[paid_plan]["processing_minutes"]
    assert usage["processing_minutes_remaining"] == PLAN_CATALOG[paid_plan]["processing_minutes"]
    assert usage["shorts_remaining"] == PLAN_CATALOG[paid_plan]["shorts"]
    assert usage["shorts_used"] == 0


@pytest.mark.parametrize("old_plan,new_plan", [
    ("creator", "growth"), ("creator", "pro"), ("growth", "agency"), ("pro", "agency"),
])
def test_same_cycle_paid_upgrade_preserves_usage(client, old_plan, new_plan):
    user_id = signup(client, f"upgrade-{old_plan}-{new_plan}@example.com")
    asyncio.run(make_recurring(user_id, old_plan, "sub_retain"))
    original = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    old_period = usage_period_key(original)
    asyncio.run(execute(
        "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?,?,?,?,?,?)",
        (f"upgraded-{old_plan}-{new_plan}", user_id, old_period, 20., 0,
         PLAN_CATALOG[old_plan]["shorts"]),
    ))
    asyncio.run(execute(
        """INSERT INTO usage_reservations(id,user_id,period_key,kind,amount,resource_id,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (f"upgrade-reservation-{old_plan}-{new_plan}", user_id, old_period, "minutes",
         20., "already-consumed-short", "finalized", START, START),
    ))
    applied = asyncio.run(_apply_provider_entity(
        original, entity("sub_retain", f"plan_{new_plan}"), allow_provider_followup=False,
    ))
    assert applied["plan"] == new_plan
    usage = client.get("/api/v1/usage").json()
    assert usage["source_minutes"] == 20.0
    assert usage["processing_minutes_remaining"] == PLAN_CATALOG[new_plan]["processing_minutes"] - 20
    assert usage["shorts_remaining"] == PLAN_CATALOG[new_plan]["shorts"] - 1


def test_new_billing_cycle_does_not_inherit_old_paid_usage(client):
    user_id = signup(client, "renewal-period@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_cycle_new"))
    old_user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    old_period = usage_period_key(old_user)
    asyncio.run(execute(
        "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?,?,?,?,?,?)",
        ("old-cycle", user_id, old_period, 56.0, 0, 15),
    ))
    # New cycle + changed tier without a pending record is provider drift,
    # not an immediate same-cycle upgrade.
    asyncio.run(_apply_provider_entity(
        old_user, entity("sub_cycle_new", "plan_growth",
                         start=END_EPOCH, end=NEXT_END_EPOCH),
        allow_provider_followup=False,
    ))
    usage = client.get("/api/v1/usage").json()
    assert usage["plan"] == "growth"
    assert usage["source_minutes"] == 0
    assert usage["processing_minutes_remaining"] == 180.0
    assert asyncio.run(fetch_one("SELECT source_minutes FROM usage WHERE id='old-cycle'"))["source_minutes"] == 56.0


@pytest.mark.parametrize("plan", list(PLAN_CATALOG))
def test_catalog_minute_and_short_limits_are_positive_and_consistent(plan):
    limits = PLAN_CATALOG[plan]
    assert limits["processing_minutes"] > 0
    assert limits["shorts"] > 0
    if plan != "free":
        assert limits["unlimited_exports"] is True



@pytest.mark.parametrize("plan", ["creator", "growth", "pro", "agency"])
def test_subscription_renewal_starts_fresh_allowance(client, plan):
    user_id = signup(client, f"renew-{plan}@example.com")
    asyncio.run(make_recurring(user_id, plan, "sub_renew_all"))
    old_user = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    old_period = usage_period_key(old_user)
    asyncio.run(execute(
        "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?,?,?,?,?,?)",
        (f"old-{plan}", user_id, old_period, 20., 0, PLAN_CATALOG[plan]["shorts"]),
    ))
    asyncio.run(execute(
        """INSERT INTO usage_reservations(id,user_id,period_key,kind,amount,resource_id,status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (f"oldres-{plan}", user_id, old_period, "minutes",
         20., f"prior-clip-{plan}", "finalized", START, START),
    ))
    current = asyncio.run(_apply_provider_entity(
        old_user, entity("sub_renew_all", f"plan_{plan}",
                         start=END_EPOCH, end=NEXT_END_EPOCH),
        allow_provider_followup=False,
    ))
    assert current["plan"] == plan
    new_period = usage_period_key(current)
    assert new_period != old_period
    latest = client.get("/api/v1/usage").json()
    assert latest["processing_minutes_remaining"] == PLAN_CATALOG[plan]["processing_minutes"]
    assert latest["shorts_remaining"] == PLAN_CATALOG[plan]["shorts"]
    prior = asyncio.run(fetch_one(
        "SELECT period_key FROM usage_reservations WHERE id=?", (f"oldres-{plan}",),
    ))
    assert prior["period_key"] == old_period

def test_immediate_cancellation_is_not_assumed_to_be_cycle_end(client):
    user_id = signup(client, "cancel-provider-confirmed@example.com")
    asyncio.run(make_recurring(user_id, "creator", "sub_cancel_now"))
    current = asyncio.run(fetch_one("SELECT * FROM users WHERE id=?", (user_id,)))
    cancelled = entity("sub_cancel_now", "plan_creator", status="cancelled")
    asyncio.run(_apply_provider_entity(current, cancelled, allow_provider_followup=False))
    stored = asyncio.run(fetch_one("SELECT plan FROM users WHERE id=?", (user_id,)))
    assert stored["plan"] == "free"

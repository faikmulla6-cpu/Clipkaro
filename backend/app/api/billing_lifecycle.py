from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import get_settings
from app.core.database import execute, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.billing import (
    PAID_PLANS,
    PLAN_CATALOG,
    SUBSCRIPTION_PLANS,
    activate_entitlement,
    downgrade_to_free,
    ensure_razorpay_plan,
    iso_from_epoch,
    parse_iso,
    razorpay_request,
    usage_period_key,
    utc_now,
    verify_order_signature,
    verify_subscription_signature,
)
from app.services.legal import checkout_allowed, has_current_legal_acceptance

router = APIRouter()
logger = logging.getLogger("clipkaro.billing")
_change_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_checkout_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _require_new_paid_commitment_ready(user_id: str) -> None:
    """Require current legal acceptance before creating/increasing paid spend.

    Public operator/grievance completeness is governed separately by
    ``checkout_allowed`` so explicit local Razorpay LIVE testing can remain
    possible without weakening production launch gates. Users are never forced
    to accept new terms merely to cancel or downgrade an existing subscription.
    """
    allowed, reason = checkout_allowed()
    if not allowed:
        raise HTTPException(403, reason)
    if not await has_current_legal_acceptance(user_id):
        raise HTTPException(
            403,
            "Review and accept the current Terms, Privacy Notice and Refund Policy before starting or increasing a paid plan.",
        )


async def init_subscription_lifecycle() -> None:
    """Create durable pending-plan state without requiring a destructive migration."""
    await execute(
        """CREATE TABLE IF NOT EXISTS subscription_plan_changes (
             user_id TEXT PRIMARY KEY,
             subscription_id TEXT NOT NULL,
             from_plan TEXT NOT NULL,
             to_plan TEXT NOT NULL,
             change_kind TEXT NOT NULL CHECK(change_kind IN ('downgrade','cancel')),
             provider_plan_id TEXT,
             effective_at TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL,
             FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
           )"""
    )
    await execute(
        "CREATE INDEX IF NOT EXISTS idx_subscription_plan_changes_subscription ON subscription_plan_changes(subscription_id)"
    )
    await execute(
        """CREATE TABLE IF NOT EXISTS billing_webhook_state (
             subscription_id TEXT PRIMARY KEY,
             last_event_created_at INTEGER NOT NULL DEFAULT 0,
             last_event_id TEXT,
             terminal INTEGER NOT NULL DEFAULT 0 CHECK(terminal IN (0,1)),
             last_status TEXT,
             updated_at TEXT NOT NULL
           )"""
    )


async def _audit(user_id: str | None, event: str, entity_type: str = "", entity_id: str = "", metadata: dict | None = None) -> None:
    await execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, event, entity_type, entity_id, json.dumps(metadata or {}), utc_now().isoformat()),
    )


def _plan_price(plan: str) -> int:
    return int((PLAN_CATALOG.get(plan) or {}).get("price_paise") or 0)


def _epoch_to_iso(value: Any) -> str | None:
    try:
        return iso_from_epoch(int(value)) if value else None
    except (TypeError, ValueError):
        return None


async def _pending_change(user_id: str) -> dict[str, Any] | None:
    await init_subscription_lifecycle()
    return await fetch_one("SELECT * FROM subscription_plan_changes WHERE user_id=?", (user_id,))


async def _clear_pending_change(user_id: str) -> None:
    await execute("DELETE FROM subscription_plan_changes WHERE user_id=?", (user_id,))


async def _save_pending_change(
    user: dict[str, Any],
    *,
    to_plan: str,
    kind: str,
    provider_plan_id: str | None,
    effective_at: str | None,
) -> None:
    timestamp = utc_now().isoformat()
    await execute(
        """INSERT INTO subscription_plan_changes(
               user_id,subscription_id,from_plan,to_plan,change_kind,provider_plan_id,effective_at,created_at,updated_at
             ) VALUES (?,?,?,?,?,?,?,?,?)
             ON CONFLICT(user_id) DO UPDATE SET
               subscription_id=excluded.subscription_id,
               from_plan=excluded.from_plan,
               to_plan=excluded.to_plan,
               change_kind=excluded.change_kind,
               provider_plan_id=excluded.provider_plan_id,
               effective_at=excluded.effective_at,
               updated_at=excluded.updated_at""",
        (
            user["id"], str(user.get("billing_reference") or ""), str(user.get("plan") or "free"),
            to_plan, kind, provider_plan_id, effective_at, timestamp, timestamp,
        ),
    )


async def _resolve_plan(entity: dict[str, Any], fallback: str | None = None) -> str | None:
    """Resolve a recurring plan only from server/provider-bound identifiers.

    Razorpay notes are useful human-readable context, but they are not an
    entitlement authority.  The provider plan id is mapped through the local
    ``billing_plans`` table created by ClipKaro.  A caller-supplied fallback is
    accepted only when it is already a locally trusted current plan.
    """
    provider_plan_id = str(entity.get("plan_id") or "")
    if provider_plan_id:
        mapped = await fetch_one("SELECT plan_key FROM billing_plans WHERE provider_plan_id=?", (provider_plan_id,))
        plan = str((mapped or {}).get("plan_key") or "")
        if plan in SUBSCRIPTION_PLANS:
            return plan
    return fallback if fallback in SUBSCRIPTION_PLANS else None


async def _subscription_checkout(entity: dict[str, Any]) -> dict[str, Any] | None:
    reference = str(entity.get("id") or "")
    if not reference:
        return None
    return await fetch_one(
        "SELECT * FROM billing_checkouts WHERE provider_reference=? AND kind='subscription'",
        (reference,),
    )


async def _user_for_subscription(entity: dict[str, Any]) -> dict[str, Any] | None:
    """Bind webhook subscription data to a user through local durable state.

    Never use provider ``notes.user_id`` as authorization.  New subscriptions
    always have a server-created ``billing_checkouts`` row.  Existing activated
    subscriptions can additionally be resolved by the user's stored
    ``billing_reference`` for backwards compatibility.
    """
    reference = str(entity.get("id") or "")
    if not reference:
        return None
    checkout = await _subscription_checkout(entity)
    if checkout:
        return await fetch_one("SELECT * FROM users WHERE id=?", (checkout["user_id"],))
    return await fetch_one("SELECT * FROM users WHERE billing_reference=?", (reference,))


def _effective_at(entity: dict[str, Any], user: dict[str, Any]) -> str | None:
    return (
        _epoch_to_iso(entity.get("change_scheduled_at"))
        or _epoch_to_iso(entity.get("current_end"))
        or user.get("plan_expires_at")
    )


async def _provider_scheduled_target(subscription_id: str) -> tuple[str | None, str | None]:
    try:
        scheduled = await razorpay_request("GET", f"/subscriptions/{subscription_id}/retrieve_scheduled_changes")
    except RuntimeError:
        return None, None
    return await _resolve_plan(scheduled), str(scheduled.get("plan_id") or "") or None


async def _cancel_provider_scheduled_update(subscription_id: str) -> None:
    await razorpay_request("POST", f"/subscriptions/{subscription_id}/cancel_scheduled_changes")


async def _migrate_usage_and_activate(
    user: dict[str, Any],
    target_plan: str,
    entity: dict[str, Any],
) -> dict[str, Any]:
    """Apply a same-cycle plan change without gifting a fresh quota bucket.

    Razorpay prorates the money. ClipKaro carries already-used Karo Minutes,
    export usage and in-flight reservations into the upgraded plan period.
    The entire local migration is retried atomically if SQLite is temporarily
    busy, so plan state and usage cannot split across lock failures.
    """
    reference = str(entity.get("id") or user.get("billing_reference") or "")
    started = _epoch_to_iso(entity.get("current_start")) or user.get("plan_started_at") or utc_now().isoformat()
    expires = _epoch_to_iso(entity.get("current_end")) or user.get("plan_expires_at")
    old_key = usage_period_key(user)
    new_user = {**user, "plan": target_plan, "billing_reference": reference, "plan_started_at": started}
    new_key = usage_period_key(new_user)
    export_limit = int(PLAN_CATALOG[target_plan]["exports"])
    now_iso = utc_now().isoformat()

    async def _migrate(db) -> None:
        old_usage = await (await db.execute(
            "SELECT * FROM usage WHERE user_id=? AND month=?", (user["id"], old_key)
        )).fetchone()
        new_usage = None
        if new_key != old_key:
            new_usage = await (await db.execute(
                "SELECT * FROM usage WHERE user_id=? AND month=?", (user["id"], new_key)
            )).fetchone()

        if old_usage and new_key != old_key:
            if new_usage:
                # A retry may find a destination period created by an earlier
                # independent operation. Use maxima rather than summing so
                # usage cannot be charged twice.
                await db.execute(
                    """UPDATE usage SET source_minutes=MAX(source_minutes,?),
                       exports_used=MAX(exports_used,?),exports_limit=? WHERE id=?""",
                    (float(old_usage["source_minutes"]), int(old_usage["exports_used"]), export_limit, new_usage["id"]),
                )
                await db.execute("DELETE FROM usage WHERE id=?", (old_usage["id"],))
            else:
                await db.execute(
                    "UPDATE usage SET month=?,exports_limit=? WHERE id=?",
                    (new_key, export_limit, old_usage["id"]),
                )
            await db.execute(
                "UPDATE usage_reservations SET period_key=?,updated_at=? WHERE user_id=? AND period_key=?",
                (new_key, now_iso, user["id"], old_key),
            )
        else:
            await db.execute(
                "UPDATE usage SET exports_limit=? WHERE user_id=? AND month=?",
                (export_limit, user["id"], new_key),
            )

        await db.execute(
            """UPDATE users SET plan=?,billing_reference=?,plan_started_at=?,plan_expires_at=?,
               cancel_at_period_end=0,updated_at=? WHERE id=?""",
            (target_plan, reference, started, expires, now_iso, user["id"]),
        )
        await db.execute("DELETE FROM subscription_plan_changes WHERE user_id=?", (user["id"],))

    await run_in_transaction(
        _migrate,
        mode="IMMEDIATE",
        operation_name="subscription plan and usage migration",
    )
    return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or new_user


async def _apply_provider_entity(
    user: dict[str, Any], entity: dict[str, Any], *, allow_provider_followup: bool = True
) -> dict[str, Any]:
    """Reconcile provider truth without confusing downgrades with cancellations.

    Webhook handlers pass ``allow_provider_followup=False`` so a signed webhook
    never blocks its acknowledgement on an outbound Razorpay API request. The
    provider's webhook guidance uses a short response timeout and retries failed
    deliveries; local DB reconciliation therefore stays on the critical path,
    while scheduled-change discovery can happen during normal billing sync.
    """
    await init_subscription_lifecycle()
    status = str(entity.get("status") or "")
    pending = await _pending_change(str(user["id"]))
    resolved_plan = await _resolve_plan(entity, str(user.get("plan") or ""))
    reference = str(entity.get("id") or user.get("billing_reference") or "")
    current_start = _epoch_to_iso(entity.get("current_start")) or user.get("plan_started_at")
    current_end = _epoch_to_iso(entity.get("current_end")) or user.get("plan_expires_at")

    if status in {"cancelled", "completed", "expired"}:
        await downgrade_to_free(str(user["id"]))
        await _clear_pending_change(str(user["id"]))
        return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user

    if status == "halted":
        end = parse_iso(current_end)
        if not end or end <= utc_now():
            await downgrade_to_free(str(user["id"]))
            await _clear_pending_change(str(user["id"]))
            return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        return user

    if status in {"authenticated", "pending", "paused"}:
        boundary = parse_iso(current_end)
        if boundary and boundary <= utc_now():
            await downgrade_to_free(str(user["id"]))
            await _clear_pending_change(str(user["id"]))
            return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user

        if status == "paused":
            # A pause stops future collection but does not erase a period the
            # customer has already paid for. Preserve entitlement through the
            # provider's current_end and keep the billing reference/dates truthful.
            # Resumption is delivered with status=active and follows the normal path.
            if str(user.get("billing_reference") or "") == reference:
                await execute(
                    "UPDATE users SET plan_started_at=?,plan_expires_at=?,updated_at=? WHERE id=?",
                    (current_start, current_end, utc_now().isoformat(), user["id"]),
                )
                return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
            return user

        # ``authenticated`` is mandate/authentication state and ``pending`` is
        # a collection-retry state. Neither is proof that a new plan/cycle has
        # been paid. Keep the established entitlement unchanged until Razorpay
        # returns active/charged provider truth. This also prevents a pending
        # scheduled plan id from being applied early during periodic sync.
        return user

    if status != "active":
        return user

    if resolved_plan and resolved_plan != user.get("plan"):
        if pending and str(pending.get("to_plan")) == resolved_plan:
            # A scheduled downgrade has become live at the new billing cycle.
            await activate_entitlement(
                str(user["id"]), resolved_plan, reference,
                period_start=current_start, period_end=current_end,
                cancel_at_period_end=False,
            )
            await _clear_pending_change(str(user["id"]))
            user = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        else:
            # Provider/local drift (for example a successful immediate upgrade whose
            # response was lost) is reconciled without resetting current usage.
            user = await _migrate_usage_and_activate(user, resolved_plan, entity)
    else:
        # Keep billing dates fresh, but do not map generic provider
        # has_scheduled_changes to ClipKaro's cancellation flag.
        await execute(
            "UPDATE users SET billing_reference=?,plan_started_at=?,plan_expires_at=?,updated_at=? WHERE id=?",
            (reference or user.get("billing_reference"), current_start, current_end, utc_now().isoformat(), user["id"]),
        )
        user = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user

    has_scheduled = bool(entity.get("has_scheduled_changes"))
    pending = await _pending_change(str(user["id"]))
    if has_scheduled and not pending and not bool(user.get("cancel_at_period_end", 0)) and allow_provider_followup:
        target, provider_plan_id = await _provider_scheduled_target(reference)
        if target and target != user.get("plan"):
            await _save_pending_change(
                user, to_plan=target, kind="downgrade", provider_plan_id=provider_plan_id,
                effective_at=_effective_at(entity, user),
            )
    elif not has_scheduled and pending and pending.get("change_kind") == "downgrade" and resolved_plan == user.get("plan"):
        # The pending provider update was cancelled externally.
        await _clear_pending_change(str(user["id"]))

    return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user


async def reconcile_subscription(user: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    plan = str(user.get("plan") or "free")
    reference = str(user.get("billing_reference") or "")
    if plan not in SUBSCRIPTION_PLANS or not reference.startswith("sub_"):
        return user

    pending = await _pending_change(str(user["id"]))
    expiry = parse_iso(user.get("plan_expires_at"))
    pending_at = parse_iso(str((pending or {}).get("effective_at") or ""))
    due = (expiry is not None and expiry <= utc_now()) or (pending_at is not None and pending_at <= utc_now())
    if not force and not due:
        return user

    try:
        entity = await razorpay_request("GET", f"/subscriptions/{reference}")
    except RuntimeError:
        # Provider outages never remove paid access locally.
        return user
    return await _apply_provider_entity(user, entity)


async def _change_subscription_plan(user: dict[str, Any], target_plan: str) -> dict[str, Any]:
    await init_subscription_lifecycle()
    async with _change_locks[str(user["id"])]:
        fresh = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        fresh = await reconcile_subscription(fresh, force=True)
        reference = str(fresh.get("billing_reference") or "")
        current_plan = str(fresh.get("plan") or "free")
        if current_plan not in SUBSCRIPTION_PLANS or not reference.startswith("sub_"):
            raise HTTPException(409, "There is no active recurring ClipKaro subscription to change.")

        pending = await _pending_change(str(fresh["id"]))
        if bool(fresh.get("cancel_at_period_end", 0)) or (pending and pending.get("change_kind") == "cancel"):
            if target_plan == "free":
                return {
                    "kind": "subscription_change", "change": "scheduled_cancellation",
                    "plan": current_plan, "target_plan": "free",
                    "effective_at": (pending or {}).get("effective_at") or fresh.get("plan_expires_at"),
                }
            raise HTTPException(
                409,
                "This subscription is already scheduled to end. Razorpay does not allow a scheduled cancellation to be reactivated; start a new subscription after it ends.",
            )

        if target_plan == "mini_pass":
            raise HTTPException(422, "Mini Pass is a one-time pass and cannot replace an active subscription. It becomes available after the subscription ends.")
        if target_plan != "free" and target_plan not in SUBSCRIPTION_PLANS:
            raise HTTPException(422, "Choose a valid ClipKaro plan.")

        if target_plan == current_plan:
            if pending and pending.get("change_kind") == "downgrade":
                await _require_new_paid_commitment_ready(str(fresh["id"]))
                try:
                    await _cancel_provider_scheduled_update(reference)
                except RuntimeError as exc:
                    raise HTTPException(502, "Razorpay could not cancel the scheduled downgrade. Please retry.") from exc
                await _clear_pending_change(str(fresh["id"]))
                await _audit(fresh["id"], "billing.downgrade_cancelled", "subscription", reference, {"plan": current_plan})
                return {"kind": "subscription_change", "change": "scheduled_change_cancelled", "plan": current_plan, "target_plan": current_plan}
            raise HTTPException(409, "This plan is already active on your account.")

        if pending and pending.get("change_kind") == "downgrade":
            if target_plan == pending.get("to_plan"):
                return {
                    "kind": "subscription_change", "change": "scheduled_downgrade",
                    "plan": current_plan, "target_plan": target_plan, "effective_at": pending.get("effective_at"),
                }
            try:
                await _cancel_provider_scheduled_update(reference)
            except RuntimeError as exc:
                raise HTTPException(502, "Razorpay could not replace the existing scheduled plan change. Please retry.") from exc
            await _clear_pending_change(str(fresh["id"]))

        if target_plan == "free":
            try:
                entity = await razorpay_request(
                    "POST", f"/subscriptions/{reference}/cancel", json_body={"cancel_at_cycle_end": True},
                )
            except RuntimeError as exc:
                raise HTTPException(502, "Razorpay could not schedule the subscription cancellation. Please retry.") from exc
            effective = _effective_at(entity, fresh)
            await _save_pending_change(fresh, to_plan="free", kind="cancel", provider_plan_id=None, effective_at=effective)
            await execute("UPDATE users SET cancel_at_period_end=1,updated_at=? WHERE id=?", (utc_now().isoformat(), fresh["id"]))
            await _audit(fresh["id"], "billing.cancellation_scheduled", "subscription", reference, {"plan": current_plan, "effective_at": effective})
            return {
                "kind": "subscription_change", "change": "scheduled_cancellation",
                "plan": current_plan, "target_plan": "free", "effective_at": effective,
            }

        is_upgrade = _plan_price(target_plan) > _plan_price(current_plan)
        if is_upgrade:
            await _require_new_paid_commitment_ready(str(fresh["id"]))
        target_provider_plan = await ensure_razorpay_plan(target_plan)
        schedule = "now" if is_upgrade else "cycle_end"
        try:
            entity = await razorpay_request(
                "PATCH", f"/subscriptions/{reference}",
                json_body={"plan_id": target_provider_plan, "schedule_change_at": schedule, "customer_notify": True},
            )
        except RuntimeError as exc:
            action = "upgrade" if is_upgrade else "downgrade"
            raise HTTPException(502, f"Razorpay could not {action} the subscription. No ClipKaro plan change was applied.") from exc

        if str(entity.get("id") or reference) != reference:
            raise HTTPException(502, "Razorpay returned an unexpected subscription reference. No local plan change was applied.")

        if is_upgrade:
            provider_plan = str(entity.get("plan_id") or "")
            if provider_plan != target_provider_plan:
                # A successful immediate update must return the target plan. If not,
                # fail closed and let /billing/sync reconcile provider truth.
                raise HTTPException(502, "Razorpay has not confirmed the upgraded plan yet. Refresh billing before retrying.")
            upgraded = await _migrate_usage_and_activate(fresh, target_plan, entity)
            await _audit(
                fresh["id"], "billing.subscription_upgraded", "subscription", reference,
                {"from_plan": current_plan, "to_plan": target_plan, "usage_preserved": True},
            )
            return {
                "kind": "subscription_change", "change": "immediate_upgrade",
                "plan": upgraded.get("plan", target_plan), "target_plan": target_plan,
                "effective_at": utc_now().isoformat(),
            }

        if not bool(entity.get("has_scheduled_changes")) and str(entity.get("schedule_change_at") or "") != "cycle_end":
            raise HTTPException(502, "Razorpay did not confirm the end-of-cycle downgrade. No local downgrade was scheduled.")
        effective = _effective_at(entity, fresh)
        await _save_pending_change(
            fresh, to_plan=target_plan, kind="downgrade", provider_plan_id=target_provider_plan, effective_at=effective,
        )
        await execute("UPDATE users SET cancel_at_period_end=0,updated_at=? WHERE id=?", (utc_now().isoformat(), fresh["id"]))
        await _audit(
            fresh["id"], "billing.downgrade_scheduled", "subscription", reference,
            {"from_plan": current_plan, "to_plan": target_plan, "effective_at": effective},
        )
        return {
            "kind": "subscription_change", "change": "scheduled_downgrade",
            "plan": current_plan, "target_plan": target_plan, "effective_at": effective,
        }


async def _billing_status_payload(user: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    user = await reconcile_subscription(user, force=force)
    pending = await _pending_change(str(user["id"]))
    scheduled_plan = str((pending or {}).get("to_plan") or ("free" if user.get("cancel_at_period_end") else "")) or None
    return {
        "plan": user["plan"],
        "billing_reference": user.get("billing_reference"),
        "plan_started_at": user.get("plan_started_at"),
        "plan_expires_at": user.get("plan_expires_at"),
        "cancel_at_period_end": bool(user.get("cancel_at_period_end", 0)),
        "scheduled_plan": scheduled_plan,
        "scheduled_plan_effective_at": (pending or {}).get("effective_at") or (user.get("plan_expires_at") if scheduled_plan == "free" else None),
        "scheduled_change_type": (pending or {}).get("change_kind") or ("cancel" if scheduled_plan == "free" else None),
    }


@router.get("/billing/status")
async def billing_status(user: dict = Depends(current_user)) -> dict[str, Any]:
    return await _billing_status_payload(user)


def _checkout_payload(user: dict[str, Any], plan: str, kind: str, reference: str) -> dict[str, Any]:
    settings = get_settings()
    catalog = PLAN_CATALOG[plan]
    response: dict[str, Any] = {
        "key_id": settings.razorpay_key_id, "kind": kind, "plan": plan, "plan_name": catalog["name"],
        "amount": catalog["price_paise"], "currency": "INR", "name": "ClipKaro AI",
        "description": f"{catalog['name']} {'Pass' if kind == 'one_time' else 'monthly subscription'}",
        "prefill": {"name": user["name"], "email": user["email"]},
    }
    response["order_id" if kind == "one_time" else "subscription_id"] = reference
    return response


async def _recent_reusable_checkout(user_id: str, plan: str, kind: str) -> dict[str, Any] | None:
    """Return a fresh unfinished provider object for safe checkout retries.

    Double-clicks, browser retries and transient frontend failures must not create
    multiple recurring subscriptions for the same user/plan.  We reuse only a
    short-lived server-created checkout in a non-terminal state.
    """
    row = await fetch_one(
        """SELECT * FROM billing_checkouts
           WHERE user_id=? AND plan=? AND kind=? AND status IN ('created','authorized')
           ORDER BY created_at DESC LIMIT 1""",
        (user_id, plan, kind),
    )
    if not row:
        return None
    created = parse_iso(str(row.get("created_at") or ""))
    if not created or utc_now() - created > timedelta(minutes=15):
        return None
    return row


@router.post("/billing/checkout")
async def billing_checkout(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    plan = str(body.get("plan", "")).lower()
    current_plan = str(user.get("plan") or "free")
    active_reference = str(user.get("billing_reference") or "")

    if current_plan in SUBSCRIPTION_PLANS and active_reference.startswith("sub_"):
        return await _change_subscription_plan(user, plan)

    if plan not in PAID_PLANS:
        raise HTTPException(422, "Choose a valid paid plan.")
    if current_plan == plan:
        raise HTTPException(409, "This plan is already active on your account.")

    # New paid commitments always require the current user acceptance. Public
    # legal-operator readiness remains environment/mode aware inside the same
    # server-side gate; the frontend is never the sole enforcement point.
    await _require_new_paid_commitment_ready(str(user["id"]))

    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        mode = settings.normalized_razorpay_mode
        raise HTTPException(503, f"Razorpay {mode} credentials are not configured on the server.")

    # Serialize checkout creation per user. This prevents a double-click, HTTP
    # retry or two browser tabs from creating multiple recurring subscriptions
    # before the first provider reference is durably stored.
    async with _checkout_locks[str(user["id"])]:
        fresh = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        fresh_plan = str(fresh.get("plan") or "free")
        fresh_reference = str(fresh.get("billing_reference") or "")
        if fresh_plan in SUBSCRIPTION_PLANS and fresh_reference.startswith("sub_"):
            return await _change_subscription_plan(fresh, plan)
        if fresh_plan == plan:
            raise HTTPException(409, "This plan is already active on your account.")

        catalog = PLAN_CATALOG[plan]
        kind = "one_time" if catalog["billing"] == "one_time" else "subscription"
        reusable = await _recent_reusable_checkout(str(fresh["id"]), plan, kind)
        if reusable:
            await _audit(
                fresh["id"], "billing.checkout_reused", kind, str(reusable["provider_reference"]),
                {"plan": plan},
            )
            return _checkout_payload(fresh, plan, kind, str(reusable["provider_reference"]))

        try:
            if kind == "one_time":
                receipt = f"ck_{fresh['id'][:8]}_{uuid.uuid4().hex[:12]}"
                data = await razorpay_request(
                    "POST", "/orders",
                    json_body={
                        "amount": catalog["price_paise"], "currency": "INR", "receipt": receipt,
                        "notes": {"user_id": fresh["id"], "plan": plan, "product": "ClipKaro AI"},
                    },
                )
                reference = str(data["id"])
            else:
                provider_plan_id = await ensure_razorpay_plan(plan)
                data = await razorpay_request(
                    "POST", "/subscriptions",
                    json_body={
                        "plan_id": provider_plan_id, "total_count": 120, "quantity": 1, "customer_notify": True,
                        "notes": {"user_id": fresh["id"], "plan": plan, "product": "ClipKaro AI"},
                    },
                )
                reference = str(data["id"])
        except RuntimeError as exc:
            logger.warning("Razorpay checkout creation failed error_type=%s", type(exc).__name__)
            raise HTTPException(502, "Razorpay could not start checkout. Please retry in a moment.") from exc

        await execute(
            """INSERT INTO billing_checkouts(id,user_id,kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at)
               VALUES (?,?,?,?,?,?,'created',NULL,?,NULL)""",
            (str(uuid.uuid4()), fresh["id"], kind, plan, reference, catalog["price_paise"], utc_now().isoformat()),
        )
        await _audit(fresh["id"], "billing.checkout_created", kind, reference, {"plan": plan, "amount": catalog["price_paise"]})
        return _checkout_payload(fresh, plan, kind, reference)



def _provider_payment_matches_checkout(payment: dict[str, Any], checkout: dict[str, Any], payment_id: str) -> tuple[bool, bool]:
    """Return (identity_valid, captured) for a server-fetched one-time payment.

    Checkout HMAC proves the browser response is authentic; entitlement still
    requires provider truth that the exact payment/order/amount/currency was
    captured. Authorized-but-uncaptured payments remain pending and can be
    completed later by the signed payment.captured/order.paid webhook.
    """
    expected_amount = int(checkout.get("amount") or 0)
    expected_order = str(checkout.get("provider_reference") or "")
    identity_valid = bool(
        str(payment.get("id") or "") == payment_id
        and str(payment.get("order_id") or "") == expected_order
        and int(payment.get("amount") or 0) == expected_amount
        and str(payment.get("currency") or "").upper() == "INR"
    )
    captured = identity_valid and (
        str(payment.get("status") or "").lower() == "captured"
        and bool(payment.get("captured", True))
    )
    return identity_valid, captured


@router.post("/billing/verify")
async def billing_verify(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    """Verify Razorpay checkout proof and activate only provider-confirmed entitlements."""
    payment_id = str(body.get("razorpay_payment_id") or "")
    signature = str(body.get("razorpay_signature") or "")
    order_id = str(body.get("razorpay_order_id") or "")
    subscription_id = str(body.get("razorpay_subscription_id") or "")
    reference = subscription_id or order_id
    if not payment_id or not signature or not reference:
        raise HTTPException(422, "Razorpay payment verification data is incomplete.")

    checkout = await fetch_one(
        "SELECT * FROM billing_checkouts WHERE provider_reference=? AND user_id=?",
        (reference, user["id"]),
    )
    if not checkout:
        raise HTTPException(404, "This checkout does not belong to your ClipKaro account.")
    if checkout["status"] == "verified":
        # A verified checkout is historical payment truth, not a perpetual
        # entitlement. Mini Passes expire and subscriptions can later end, so a
        # replayed old browser callback must not tell the UI that access is still
        # active after the user's current entitlement has changed.
        current = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        activated = (
            str(current.get("plan") or "") == str(checkout.get("plan") or "")
            and str(current.get("billing_reference") or "") == str(checkout.get("provider_reference") or "")
            and (
                parse_iso(current.get("plan_expires_at")) is None
                or parse_iso(current.get("plan_expires_at")) > utc_now()
            )
        )
        return {"verified": True, "activated": activated, "plan": checkout["plan"]}

    plan = str(checkout["plan"])
    stored_reference = str(checkout["provider_reference"])
    if checkout["kind"] == "one_time":
        if not order_id or order_id != stored_reference or not verify_order_signature(stored_reference, payment_id, signature):
            raise HTTPException(400, "Payment signature verification failed.")
        try:
            provider_payment = await razorpay_request("GET", f"/payments/{payment_id}")
        except RuntimeError as exc:
            # Never grant an entitlement only from a browser callback when the
            # provider status cannot be confirmed. A signed webhook may recover
            # the checkout later after capture.
            raise HTTPException(502, "Payment was authenticated, but capture status could not be confirmed. Refresh billing shortly.") from exc
        identity_valid, captured = _provider_payment_matches_checkout(provider_payment, checkout, payment_id)
        if not identity_valid:
            raise HTTPException(400, "Payment details did not match this ClipKaro checkout.")
        if captured:
            activated_now = await _activate_one_time_checkout(checkout, payment_id=payment_id)
            # A signed webhook may have won the race and activated this checkout
            # just before the browser callback arrived. That is still verified.
            activated = activated_now or bool((await fetch_one(
                "SELECT status FROM billing_checkouts WHERE id=?", (checkout["id"],)
            ) or {}).get("status") == "verified")
        else:
            activated = False
            await execute(
                "UPDATE billing_checkouts SET status='authorized',payment_id=? WHERE id=? AND status!='verified'",
                (payment_id, checkout["id"]),
            )
    else:
        if not subscription_id or subscription_id != stored_reference or not verify_subscription_signature(stored_reference, payment_id, signature):
            raise HTTPException(400, "Subscription signature verification failed.")
        try:
            entity = await razorpay_request("GET", f"/subscriptions/{stored_reference}")
        except RuntimeError as exc:
            raise HTTPException(502, "Payment was received, but subscription status could not be confirmed. Refresh billing shortly.") from exc
        provider_plan_id = str(entity.get("plan_id") or "")
        expected = await fetch_one("SELECT provider_plan_id FROM billing_plans WHERE plan_key=?", (plan,))
        if not expected or provider_plan_id != str(expected["provider_plan_id"]):
            raise HTTPException(400, "Subscription plan verification failed.")
        provider_status = str(entity.get("status") or "")
        # Razorpay's successful Checkout transaction authenticates the mandate;
        # the subscription itself is paid/usable only when provider truth reaches
        # active. A later pending state explicitly represents a failed recurring
        # charge and must not bootstrap a brand-new local entitlement merely
        # because historical paid_count is non-zero. Webhooks/sync preserve an
        # already-established paid period separately.
        activated = provider_status == "active"
        if activated:
            await activate_entitlement(
                user["id"], plan, stored_reference,
                period_start=_epoch_to_iso(entity.get("current_start")),
                period_end=_epoch_to_iso(entity.get("current_end")),
                # A generic scheduled provider change may be a downgrade. It is
                # not proof that the customer scheduled cancellation. ClipKaro's
                # explicit cancellation state is maintained by lifecycle routes.
                cancel_at_period_end=False,
            )

    if checkout["kind"] != "one_time":
        await execute(
            "UPDATE billing_checkouts SET status=?,payment_id=?,verified_at=? WHERE id=?",
            ("verified" if activated else "authorized", payment_id, utc_now().isoformat(), checkout["id"]),
        )
    await _audit(user["id"], "billing.payment_verified", checkout["kind"], reference, {"plan": plan, "activated": activated})
    return {"verified": True, "activated": activated, "plan": plan}


@router.post("/billing/sync")
async def billing_sync(user: dict = Depends(current_user)) -> dict[str, Any]:
    return await _billing_status_payload(user, force=True)


@router.post("/billing/cancel")
async def billing_cancel(user: dict = Depends(current_user)) -> dict[str, Any]:
    changed = await _change_subscription_plan(user, "free")
    return {
        "cancel_at_period_end": True,
        "plan_expires_at": changed.get("effective_at"),
        "scheduled_plan": "free",
        "scheduled_plan_effective_at": changed.get("effective_at"),
    }


@router.post("/billing/cancel-scheduled-change")
async def cancel_scheduled_change(user: dict = Depends(current_user)) -> dict[str, Any]:
    await init_subscription_lifecycle()
    async with _change_locks[str(user["id"])]:
        fresh = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        pending = await _pending_change(str(fresh["id"]))
        if not pending:
            raise HTTPException(409, "There is no scheduled plan downgrade to cancel.")
        if pending.get("change_kind") == "cancel" or bool(fresh.get("cancel_at_period_end", 0)):
            raise HTTPException(409, "A scheduled subscription cancellation cannot be reactivated. Start a new subscription after it ends.")
        reference = str(fresh.get("billing_reference") or "")
        try:
            await _cancel_provider_scheduled_update(reference)
        except RuntimeError as exc:
            raise HTTPException(502, "Razorpay could not cancel the scheduled downgrade. Please retry.") from exc
        await _clear_pending_change(str(fresh["id"]))
        await _audit(fresh["id"], "billing.downgrade_cancelled", "subscription", reference, {"plan": fresh.get("plan")})
        return await _billing_status_payload(fresh)


async def _activate_one_time_checkout(
    checkout: dict[str, Any],
    *,
    payment_id: str | None,
) -> bool:
    """Atomically activate an already-authenticated one-time Razorpay checkout.

    This helper is shared by the browser signature callback and signed webhooks,
    so a lost browser callback cannot strand a successfully captured Mini Pass.
    The checkout row is re-read inside an IMMEDIATE transaction to make webhook
    retries and callback/webhook races idempotent across processes.
    """
    plan = str(checkout.get("plan") or "")
    if plan not in PLAN_CATALOG or str(PLAN_CATALOG[plan].get("billing") or "") != "one_time":
        raise ValueError("The checkout is not a valid one-time ClipKaro entitlement.")
    now = utc_now()
    started = now.isoformat()
    valid_days = int(PLAN_CATALOG[plan].get("valid_days") or 31)
    expires = (now + timedelta(days=valid_days)).isoformat()
    activated = False

    async def _apply(db) -> None:
        nonlocal activated
        current = await (await db.execute(
            "SELECT * FROM billing_checkouts WHERE id=?", (checkout["id"],)
        )).fetchone()
        if not current:
            raise ValueError("The billing checkout no longer exists.")
        if str(current["status"] or "") == "verified":
            return
        if str(current["kind"] or "") != "one_time" or str(current["plan"] or "") != plan:
            raise ValueError("The billing checkout changed unexpectedly.")
        await db.execute(
            """UPDATE users SET plan=?,billing_reference=?,plan_started_at=?,plan_expires_at=?,
               cancel_at_period_end=0,updated_at=? WHERE id=?""",
            (plan, str(current["provider_reference"]), started, expires, started, str(current["user_id"])),
        )
        await db.execute(
            "UPDATE billing_checkouts SET status='verified',payment_id=COALESCE(?,payment_id),verified_at=? WHERE id=?",
            (payment_id or None, started, str(current["id"])),
        )
        activated = True

    await run_in_transaction(_apply, mode="IMMEDIATE", operation_name="one-time billing entitlement activation")
    return activated


def _one_time_webhook_reference(event_type: str, payment: dict[str, Any], order: dict[str, Any]) -> str:
    if event_type == "payment.captured":
        return str(payment.get("order_id") or "")
    if event_type == "order.paid":
        return str(order.get("id") or payment.get("order_id") or "")
    return ""


def _one_time_webhook_payment_is_valid(
    event_type: str,
    checkout: dict[str, Any],
    payment: dict[str, Any],
    order: dict[str, Any],
) -> tuple[bool, str]:
    """Validate signed provider truth against the server-created checkout."""
    expected_amount = int(checkout.get("amount") or 0)
    reference = str(checkout.get("provider_reference") or "")
    if not reference or expected_amount <= 0:
        return False, "checkout_invalid"

    payment_order_id = str(payment.get("order_id") or "")
    if payment_order_id and payment_order_id != reference:
        return False, "order_reference_mismatch"

    if event_type == "payment.captured":
        if str(payment.get("status") or "") != "captured":
            return False, "payment_not_captured"
        amount = int(payment.get("amount") or 0)
        currency = str(payment.get("currency") or "INR").upper()
    elif event_type == "order.paid":
        if str(order.get("status") or "") != "paid":
            return False, "order_not_paid"
        amount = int(order.get("amount_paid") or order.get("amount") or 0)
        currency = str(order.get("currency") or payment.get("currency") or "INR").upper()
        if payment and str(payment.get("status") or "captured") != "captured":
            return False, "payment_not_captured"
    else:
        return False, "unsupported_event"

    if amount != expected_amount:
        return False, "amount_mismatch"
    if currency != "INR":
        return False, "currency_mismatch"
    return True, "verified"


def _one_time_payment_state_is_valid(
    checkout: dict[str, Any], payment: dict[str, Any], *, expected_status: str
) -> tuple[bool, str]:
    """Validate a non-entitling payment state against a server-created order.

    ``payment.authorized`` and ``payment.failed`` are useful operational truth,
    but neither grants a Mini Pass.  Binding them to the order/amount/currency
    lets checkout state remain diagnosable without trusting payer-controlled
    notes or accidentally treating a failed/authorised payment as captured.
    """
    reference = str(checkout.get("provider_reference") or "")
    expected_amount = int(checkout.get("amount") or 0)
    if not reference or expected_amount <= 0:
        return False, "checkout_invalid"
    if str(payment.get("order_id") or "") != reference:
        return False, "order_reference_mismatch"
    if str(payment.get("status") or "").lower() != expected_status:
        return False, f"payment_not_{expected_status}"
    try:
        amount = int(payment.get("amount") or 0)
    except (TypeError, ValueError):
        return False, "amount_mismatch"
    if amount != expected_amount:
        return False, "amount_mismatch"
    if str(payment.get("currency") or "").upper() != "INR":
        return False, "currency_mismatch"
    return True, expected_status


_SUBSCRIPTION_TERMINAL_EVENTS = {
    "subscription.cancelled", "subscription.completed", "subscription.expired",
}
# A process can die after atomically claiming a webhook but before completing it.
# Razorpay retries failed/time-out deliveries, so an orphaned claim must become
# recoverable instead of returning 503 forever. Five minutes is far longer than
# the normal webhook handler path while still providing bounded crash recovery.
_WEBHOOK_PROCESSING_CLAIM_TTL_SECONDS = 300


def _event_created_at(payload: dict[str, Any]) -> int:
    try:
        return max(0, int(payload.get("created_at") or 0))
    except (TypeError, ValueError):
        return 0


async def _subscription_webhook_should_apply(
    subscription_id: str, *, event_type: str, event_created_at: int
) -> tuple[bool, str]:
    """Reject stale/non-terminal events after durable provider state.

    Razorpay documents at-least-once delivery and explicitly warns that webhook
    events may arrive out of order.  A cancelled/completed/expired subscription
    cannot be reactivated under the same provider id, so terminal state is
    monotonic.  For ordinary updates, provider event creation time prevents an
    older delivery from reverting a later plan/cycle reconciliation.
    """
    if not subscription_id:
        return False, "missing_subscription_id"
    state = await fetch_one(
        "SELECT * FROM billing_webhook_state WHERE subscription_id=?",
        (subscription_id,),
    )
    if not state:
        return True, "new"
    if bool(state.get("terminal")) and event_type not in _SUBSCRIPTION_TERMINAL_EVENTS:
        return False, "after_terminal"
    previous_created = int(state.get("last_event_created_at") or 0)
    if event_created_at and previous_created and event_created_at < previous_created:
        return False, "out_of_order"
    return True, "current"


async def _record_subscription_webhook_state(
    subscription_id: str, *, event_id: str, event_type: str, event_created_at: int, status: str
) -> None:
    terminal = int(event_type in _SUBSCRIPTION_TERMINAL_EVENTS)
    timestamp = utc_now().isoformat()
    await execute(
        """INSERT INTO billing_webhook_state(
             subscription_id,last_event_created_at,last_event_id,terminal,last_status,updated_at
           ) VALUES (?,?,?,?,?,?)
           ON CONFLICT(subscription_id) DO UPDATE SET
             last_event_created_at=MAX(billing_webhook_state.last_event_created_at,excluded.last_event_created_at),
             last_event_id=CASE
               WHEN excluded.last_event_created_at >= billing_webhook_state.last_event_created_at
               THEN excluded.last_event_id ELSE billing_webhook_state.last_event_id END,
             terminal=MAX(billing_webhook_state.terminal,excluded.terminal),
             last_status=CASE
               WHEN excluded.last_event_created_at >= billing_webhook_state.last_event_created_at
               THEN excluded.last_status ELSE billing_webhook_state.last_status END,
             updated_at=excluded.updated_at""",
        (subscription_id, event_created_at, event_id, terminal, status[:80], timestamp),
    )


_WEBHOOK_SENSITIVE_KEYS = {
    "email", "contact", "card", "vpa", "bank", "wallet", "acquirer_data",
    "token", "auth", "authorization", "customer_id",
}


def _sanitize_webhook_payload(value: Any, *, depth: int = 0) -> Any:
    """Keep a useful payment audit trail without retaining avoidable payer details."""
    if depth > 12:
        return "[truncated]"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _WEBHOOK_SENSITIVE_KEYS:
                cleaned[str(key)] = "[redacted]"
            else:
                cleaned[str(key)] = _sanitize_webhook_payload(item, depth=depth + 1)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_webhook_payload(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…"
    return value


async def _claim_webhook_event(event_id: str, event_type: str, payload_json: str) -> str:
    """Atomically reserve a Razorpay event id before applying side effects.

    Razorpay may deliver the same webhook concurrently. A read-then-write
    idempotency check is racy, so the UNIQUE ``provider_event_id`` constraint is
    used as the authority. ``processing`` is intentionally durable only for the
    lifetime of this request; failures release the claim so Razorpay can retry.
    The return value is ``claimed``, ``processing`` or ``complete``.
    """
    timestamp = utc_now().isoformat()

    async def _claim(db) -> str:
        cursor = await db.execute(
            "SELECT status,created_at FROM payment_events WHERE provider_event_id=?",
            (event_id,),
        )
        existing = await cursor.fetchone()
        if existing:
            if str(existing["status"] or "") != "processing":
                return "complete"
            claimed_at = parse_iso(str(existing["created_at"] or ""))
            stale = claimed_at is None or (utc_now() - claimed_at).total_seconds() >= _WEBHOOK_PROCESSING_CLAIM_TTL_SECONDS
            if not stale:
                return "processing"
            # The previous worker/API process likely died after claiming the
            # event. Refresh the same UNIQUE row and let this signed retry own
            # reconciliation. No entitlement side effect from the abandoned
            # request can still be running after the configured stale window.
            await db.execute(
                """UPDATE payment_events SET event_type=?,payload_json=?,created_at=?
                   WHERE provider_event_id=? AND status='processing'""",
                (event_type, payload_json, timestamp, event_id),
            )
            return "claimed"
        await db.execute(
            """INSERT INTO payment_events(
                 id,provider_event_id,user_id,event_type,plan,amount,status,payload_json,created_at
               ) VALUES (?,?,NULL,?,NULL,0,'processing',?,?)""",
            (str(uuid.uuid4()), event_id, event_type, payload_json, timestamp),
        )
        return "claimed"

    return await run_in_transaction(_claim, mode="IMMEDIATE", operation_name="claim Razorpay webhook")


async def _release_webhook_claim(event_id: str) -> None:
    """Release only an unfinished claim so a failed delivery can be retried."""
    await execute(
        "DELETE FROM payment_events WHERE provider_event_id=? AND status='processing'",
        (event_id,),
    )


async def _complete_webhook_event(
    event_id: str, *, user_id: str | None, event_type: str, plan: str | None,
    amount: int, status: str, payload_json: str,
) -> None:
    await execute(
        """UPDATE payment_events
           SET user_id=?,event_type=?,plan=?,amount=?,status=?,payload_json=?
           WHERE provider_event_id=? AND status='processing'""",
        (user_id, event_type, plan, amount, status, payload_json, event_id),
    )


@router.post("/billing/razorpay/webhook", status_code=204)
async def razorpay_webhook(request: Request) -> Response:
    secret = get_settings().razorpay_webhook_secret
    if not secret:
        raise HTTPException(503, "Billing webhook is not configured.")
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid billing signature.")

    payload = json.loads(body)
    event_id = str(request.headers.get("X-Razorpay-Event-Id") or payload.get("event_id") or hashlib.sha256(body).hexdigest())
    event_type = str(payload.get("event") or "unknown")
    sanitized_payload_json = json.dumps(_sanitize_webhook_payload(payload))
    claim = await _claim_webhook_event(event_id, event_type, sanitized_payload_json)
    if claim == "complete":
        return Response(status_code=204)
    if claim == "processing":
        # A concurrent delivery is still mutating local entitlement state. Do
        # not acknowledge it as complete; a retry after the first request ends
        # is safer than silently losing the event if that request fails.
        raise HTTPException(503, "Billing webhook is already being processed. Please retry.")

    try:
        provider_payload = payload.get("payload", {}) if isinstance(payload.get("payload"), dict) else {}
        subscription = provider_payload.get("subscription", {}).get("entity", {}) or {}
        payment = provider_payload.get("payment", {}).get("entity", {}) or {}
        order = provider_payload.get("order", {}).get("entity", {}) or {}
        subscription_id = str(subscription.get("id") or "")
        provider_event_created_at = _event_created_at(payload)
        subscription_checkout = await _subscription_checkout(subscription) if subscription else None
        user = await _user_for_subscription(subscription) if subscription else None
        resolved_plan = await _resolve_plan(subscription, str((user or {}).get("plan") or "")) if subscription else None
        event_status = str(subscription.get("status") or payment.get("status") or order.get("status") or "received")
        subscription_event_apply = True
        subscription_event_reason = "not_subscription"
        if subscription:
            subscription_event_apply, subscription_event_reason = await _subscription_webhook_should_apply(
                subscription_id, event_type=event_type, event_created_at=provider_event_created_at
            )
            if not subscription_event_apply:
                event_status = f"ignored_{subscription_event_reason}"

        # Apply provider truth before recording idempotency. A transient reconciliation
        # error returns 5xx and Razorpay can retry instead of an event being marked done early.
        # For a newly-created subscription, bind the event to ClipKaro's server-created
        # checkout and require the provider plan id to map to the exact requested plan.
        # Provider notes are never entitlement authority.
        subscription_binding_valid = True
        if subscription_checkout:
            expected_plan = str(subscription_checkout.get("plan") or "")
            if not user or str(subscription_checkout.get("user_id") or "") != str(user.get("id") or ""):
                subscription_binding_valid = False
                event_status = "rejected_subscription_user_mismatch"
            elif not resolved_plan or resolved_plan != expected_plan:
                subscription_binding_valid = False
                event_status = "rejected_subscription_plan_mismatch"
                await _audit(
                    str(subscription_checkout["user_id"]),
                    "billing.subscription_webhook_rejected",
                    "subscription",
                    str(subscription_checkout.get("provider_reference") or ""),
                    {"expected_plan": expected_plan, "reason": "provider_plan_mismatch", "event": event_type},
                )

        official_subscription_events = {
            "subscription.authenticated", "subscription.activated", "subscription.charged",
            "subscription.completed", "subscription.updated", "subscription.pending",
            "subscription.halted", "subscription.paused", "subscription.resumed",
            "subscription.cancelled", "subscription.expired",
        }
        if user and subscription_binding_valid and subscription_event_apply and event_type in official_subscription_events:
            provider_status = str(subscription.get("status") or "")
            try:
                paid_count = max(0, int(subscription.get("paid_count") or 0))
            except (TypeError, ValueError):
                paid_count = 0
            reference_matches_user = str(user.get("billing_reference") or "") == subscription_id
            entitlement_evidence = provider_status == "active" or paid_count > 0 or reference_matches_user

            # Authenticated/updated webhooks can exist before the first paid
            # cycle. A server-created checkout proves ownership, not payment.
            # Never migrate a free user into a paid plan until Razorpay shows an
            # active subscription, at least one paid cycle, or this exact
            # subscription is already the user's established billing reference.
            if event_type in _SUBSCRIPTION_TERMINAL_EVENTS or provider_status == "halted":
                user = await _apply_provider_entity(user, subscription, allow_provider_followup=False)
            elif entitlement_evidence:
                user = await _apply_provider_entity(user, subscription, allow_provider_followup=False)
            elif subscription_checkout and provider_status == "authenticated":
                await execute(
                    "UPDATE billing_checkouts SET status='authorized' WHERE id=? AND status='created'",
                    (subscription_checkout["id"],),
                )
                event_status = "authorized"

            if subscription_checkout and event_type not in _SUBSCRIPTION_TERMINAL_EVENTS:
                # Mark the checkout verified only after local entitlement state
                # actually reflects this exact server-created subscription. A
                # pending retry may carry paid_count from older cycles, and an
                # authenticated mandate is ownership proof only; neither may turn
                # a free/new account's checkout into a false "activated" record.
                local_entitlement_active = bool(
                    user
                    and str(user.get("plan") or "") == str(subscription_checkout.get("plan") or "")
                    and str(user.get("billing_reference") or "") == subscription_id
                    and (
                        parse_iso(user.get("plan_expires_at")) is None
                        or parse_iso(user.get("plan_expires_at")) > utc_now()
                    )
                )
                if local_entitlement_active:
                    await execute(
                        """UPDATE billing_checkouts
                           SET status='verified',payment_id=COALESCE(?,payment_id),verified_at=COALESCE(verified_at,?)
                           WHERE id=? AND status!='verified'""",
                        (str(payment.get("id") or "") or None, utc_now().isoformat(), subscription_checkout["id"]),
                    )
                    event_status = "verified"
            if event_type in _SUBSCRIPTION_TERMINAL_EVENTS and subscription_checkout:
                await execute(
                    "UPDATE billing_checkouts SET status=? WHERE id=?",
                    (str(subscription.get("status") or "terminal"), subscription_checkout["id"]),
                )

        if subscription and subscription_event_apply and subscription_binding_valid:
            await _record_subscription_webhook_state(
                subscription_id,
                event_id=event_id,
                event_type=event_type,
                event_created_at=provider_event_created_at,
                status=str(subscription.get("status") or event_status),
            )

        # Track non-entitling one-time payment states from signed provider
        # webhooks. Razorpay documents both failed payments and late
        # authorisations; neither state grants access. A later captured/order.paid
        # event remains the only webhook path that can activate the Mini Pass.
        if event_type in {"payment.authorized", "payment.failed"}:
            reference = str(payment.get("order_id") or "")
            checkout = await fetch_one(
                "SELECT * FROM billing_checkouts WHERE provider_reference=? AND kind='one_time'",
                (reference,),
            ) if reference else None
            if checkout:
                expected_status = "authorized" if event_type == "payment.authorized" else "failed"
                valid_state, validation_status = _one_time_payment_state_is_valid(
                    checkout, payment, expected_status=expected_status
                )
                user = await fetch_one("SELECT * FROM users WHERE id=?", (checkout["user_id"],))
                resolved_plan = str(checkout.get("plan") or "") or None
                if valid_state:
                    await execute(
                        """UPDATE billing_checkouts SET status=?,payment_id=COALESCE(?,payment_id)
                           WHERE id=? AND status!='verified'""",
                        (expected_status, str(payment.get("id") or "") or None, checkout["id"]),
                    )
                    event_status = expected_status
                    await _audit(
                        str(checkout["user_id"]),
                        f"billing.one_time_payment_{expected_status}",
                        "one_time",
                        reference,
                        {"plan": resolved_plan, "event": event_type},
                    )
                else:
                    event_status = f"rejected_{validation_status}"
                    await _audit(
                        str(checkout["user_id"]),
                        "billing.one_time_webhook_rejected",
                        "one_time",
                        reference,
                        {"plan": resolved_plan, "reason": validation_status, "event": event_type},
                    )

        # Browser callbacks are not durable. Reconcile captured one-time orders from
        # signed Razorpay webhooks so a closed tab/network loss cannot strand a paid
        # Mini Pass. No client-provided plan/user data is trusted here.
        if event_type in {"payment.captured", "order.paid"}:
            reference = _one_time_webhook_reference(event_type, payment, order)
            checkout = await fetch_one(
                "SELECT * FROM billing_checkouts WHERE provider_reference=? AND kind='one_time'",
                (reference,),
            ) if reference else None
            if checkout:
                user = await fetch_one("SELECT * FROM users WHERE id=?", (checkout["user_id"],))
                resolved_plan = str(checkout.get("plan") or "") or None
                valid_payment, validation_status = _one_time_webhook_payment_is_valid(
                    event_type, checkout, payment, order
                )
                if valid_payment:
                    provider_payment_id = str(payment.get("id") or checkout.get("payment_id") or "") or None
                    await _activate_one_time_checkout(checkout, payment_id=provider_payment_id)
                    event_status = "verified"
                    await _audit(
                        str(checkout["user_id"]),
                        "billing.one_time_webhook_verified",
                        "one_time",
                        reference,
                        {"plan": resolved_plan, "event": event_type},
                    )
                else:
                    # A correctly signed but internally inconsistent event is retained
                    # for operations/security review without granting entitlement.
                    event_status = f"rejected_{validation_status}"
                    await _audit(
                        str(checkout["user_id"]),
                        "billing.one_time_webhook_rejected",
                        "one_time",
                        reference,
                        {"plan": resolved_plan, "reason": validation_status, "event": event_type},
                    )

        await _complete_webhook_event(
            event_id,
            user_id=(user or {}).get("id"),
            event_type=event_type,
            plan=resolved_plan,
            amount=int(payment.get("amount") or order.get("amount_paid") or order.get("amount") or 0),
            status=event_status,
            payload_json=sanitized_payload_json,
        )
        return Response(status_code=204)
    except Exception:
        # Do not strand a durable `processing` marker if reconciliation fails.
        # Releasing only unfinished claims lets Razorpay retry the same signed
        # event id without ever deleting a successfully completed audit row.
        await _release_webhook_claim(event_id)
        raise

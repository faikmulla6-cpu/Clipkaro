from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.database import execute, fetch_one


PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "price": 0,
        "price_paise": 0,
        "exports": 2,
        "shorts": 2,
        "unlimited_exports": False,
        "processing_minutes": 15,
        "resolution": "720p",
        "watermark": True,
        "billing": "free",
    },
    "mini_pass": {
        "name": "Mini Pass",
        "price": 59,
        "price_paise": 5900,
        "exports": 5,
        "shorts": 5,
        "unlimited_exports": True,
        "processing_minutes": 125,
        "source_minutes_per_short": 25,
        "resolution": "1080p",
        "watermark": False,
        "billing": "one_time",
        "valid_days": 30,
    },
    "creator": {
        "name": "Creator",
        "price": 199,
        "price_paise": 19900,
        "exports": 15,
        "shorts": 15,
        "unlimited_exports": True,
        "processing_minutes": 900,
        "source_minutes_per_short": 60,
        "resolution": "1080p",
        "watermark": False,
        "billing": "subscription",
    },
    "growth": {
        "name": "Growth",
        "price": 399,
        "price_paise": 39900,
        "exports": 50,
        "shorts": 50,
        "unlimited_exports": True,
        "processing_minutes": 9000,
        "source_minutes_per_short": 180,
        "resolution": "1080p",
        "watermark": False,
        "billing": "subscription",
        "popular": True,
    },
    "pro": {
        "name": "Pro",
        "price": 799,
        "price_paise": 79900,
        "exports": 150,
        "shorts": 150,
        "unlimited_exports": True,
        "processing_minutes": 72000,
        "source_minutes_per_short": 480,
        "resolution": "1080p",
        "watermark": False,
        "billing": "subscription",
    },
    "agency": {
        "name": "Agency",
        "price": 1999,
        "price_paise": 199900,
        "exports": 500,
        "shorts": 500,
        "unlimited_exports": True,
        "processing_minutes": 1500,
        "resolution": "1080p",
        "watermark": False,
        "billing": "subscription",
    },
}

SUBSCRIPTION_PLANS = {key for key, value in PLAN_CATALOG.items() if value["billing"] == "subscription"}
PAID_PLANS = {key for key in PLAN_CATALOG if key != "free"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_from_epoch(value: int | float | None) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def usage_period_key(user: dict[str, Any]) -> str:
    plan = str(user.get("plan") or "free")
    if plan == "free":
        return f"free:{utc_now():%Y-%m}"
    reference = str(user.get("billing_reference") or user.get("id") or "local")
    started = str(user.get("plan_started_at") or f"{utc_now():%Y-%m}")
    return f"{plan}:{reference}:{started[:19]}"


async def mini_pass_is_exhausted(user: dict[str, Any]) -> bool:
    """A Mini Pass expires for new creation as soon as its 5th source is consumed.

    Keep the underlying paid-pass marker until the retention deadline so Shorts
    created by that purchase can still be edited, exported and re-exported.
    A replacement Mini Pass receives a new billing reference/usage period.
    """
    if str(user.get("plan") or "") != "mini_pass":
        return False
    period = usage_period_key(user)
    row = await fetch_one(
        """SELECT COUNT(DISTINCT resource_id) count FROM usage_reservations
           WHERE user_id=? AND period_key=? AND kind='minutes'
             AND status IN ('reserved','finalized')""",
        (str(user["id"]), period),
    )
    limit = int(PLAN_CATALOG["mini_pass"].get("shorts") or 5)
    return int((row or {}).get("count") or 0) >= limit


def verify_order_signature(order_id: str, payment_id: str, signature: str) -> bool:
    secret = get_settings().razorpay_key_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_subscription_signature(subscription_id: str, payment_id: str, signature: str) -> bool:
    secret = get_settings().razorpay_key_secret
    if not secret:
        return False
    # Razorpay Subscriptions Standard Checkout signs payment_id|subscription_id.
    expected = hmac.new(secret.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _require_legal_before_provider_checkout(path: str, json_body: dict | None) -> None:
    """Fail before creating a user-specific Razorpay order/subscription.

    This duplicates the SQLite checkout trigger intentionally: the provider guard
    prevents orphan provider objects; the database trigger is the final authority
    if another code path ever bypasses this HTTP helper.
    """
    if path not in {"/orders", "/subscriptions"}:
        return
    notes = (json_body or {}).get("notes") or {}
    user_id = str(notes.get("user_id") or "") if isinstance(notes, dict) else ""
    if not user_id:
        return
    from app.services.legal import (
        checkout_allowed,
        has_current_legal_acceptance,
    )

    allowed, _ = checkout_allowed()
    if not allowed:
        raise RuntimeError("LEGAL_CHECKOUT_NOT_ALLOWED")
    if not await has_current_legal_acceptance(user_id):
        raise RuntimeError("LEGAL_ACCEPTANCE_REQUIRED")


async def razorpay_request(method: str, path: str, *, json_body: dict | None = None, params: dict | None = None) -> dict:
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay credentials are not configured on the server.")
    if method.upper() == "POST":
        await _require_legal_before_provider_checkout(path, json_body)
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.request(
            method,
            f"https://api.razorpay.com/v1{path}",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json=json_body,
            params=params,
        )
    if response.status_code >= 400:
        detail = ""
        try:
            payload = response.json()
            detail = str((payload.get("error") or {}).get("description") or payload.get("error") or "")
        except Exception:
            detail = response.text[:300]
        raise RuntimeError(f"Razorpay request failed ({response.status_code}){': ' + detail if detail else ''}")
    return response.json()


def razorpay_configuration_ready() -> bool:
    settings = get_settings()
    return bool(
        settings.razorpay_key_id.strip()
        and settings.razorpay_key_secret.strip()
        and settings.razorpay_webhook_secret.strip()
    )


async def probe_razorpay_readiness(*, live: bool = True) -> dict[str, object]:
    """Verify billing configuration and bounded read-only provider auth without leaking secrets."""
    settings = get_settings()
    if not razorpay_configuration_ready():
        return {"configured": False, "reachable": False, "authenticated": False, "code": "unconfigured"}
    if not live:
        return {"configured": True, "reachable": True, "authenticated": True, "code": "configured"}
    timeout = min(max(2.0, float(settings.preflight_network_timeout_seconds)), 10.0)
    try:
        # Plans is a read-only request and creates no billing/provider state.
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://api.razorpay.com/v1/plans",
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                params={"count": 1},
            )
    except (httpx.TimeoutException, httpx.RequestError):
        return {"configured": True, "reachable": False, "authenticated": False, "code": "unreachable"}
    if response.status_code in {401, 403}:
        return {"configured": True, "reachable": True, "authenticated": False, "code": "credentials_rejected"}
    if response.status_code >= 400:
        return {"configured": True, "reachable": True, "authenticated": False, "code": "provider_error"}
    return {"configured": True, "reachable": True, "authenticated": True, "code": "ready"}


async def ensure_razorpay_plan(plan_key: str) -> str:
    if plan_key not in SUBSCRIPTION_PLANS:
        raise ValueError("This is not a recurring plan.")
    existing = await fetch_one("SELECT provider_plan_id FROM billing_plans WHERE plan_key=?", (plan_key,))
    if existing:
        return str(existing["provider_plan_id"])

    plan = PLAN_CATALOG[plan_key]
    expected_name = f"ClipKaro {plan['name']} — ₹{plan['price']}/month"

    # Reuse an already-created matching live plan when a database has been reset.
    try:
        fetched = await razorpay_request("GET", "/plans", params={"count": 100})
        for item in fetched.get("items", []):
            details = item.get("item") or {}
            notes = item.get("notes") or {}
            if (
                item.get("period") == "monthly"
                and int(item.get("interval") or 0) == 1
                and int(details.get("amount") or 0) == int(plan["price_paise"])
                and details.get("currency") == "INR"
                and (notes.get("clipkaro_plan") == plan_key or details.get("name") == expected_name)
            ):
                provider_id = str(item["id"])
                await execute(
                    "INSERT OR REPLACE INTO billing_plans(plan_key,provider_plan_id,amount,currency,created_at) VALUES (?,?,?,?,?)",
                    (plan_key, provider_id, plan["price_paise"], "INR", utc_now().isoformat()),
                )
                return provider_id
    except RuntimeError:
        # The create call below will return the useful provider error if Razorpay is unavailable.
        pass

    created = await razorpay_request(
        "POST",
        "/plans",
        json_body={
            "period": "monthly",
            "interval": 1,
            "item": {
                "name": expected_name,
                "amount": plan["price_paise"],
                "currency": "INR",
                "description": f"ClipKaro AI {plan['name']} monthly subscription",
            },
            "notes": {"clipkaro_plan": plan_key, "product": "ClipKaro AI"},
        },
    )
    provider_id = str(created["id"])
    await execute(
        "INSERT OR REPLACE INTO billing_plans(plan_key,provider_plan_id,amount,currency,created_at) VALUES (?,?,?,?,?)",
        (plan_key, provider_id, plan["price_paise"], "INR", utc_now().isoformat()),
    )
    return provider_id


async def activate_entitlement(
    user_id: str,
    plan_key: str,
    reference: str,
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    cancel_at_period_end: bool = False,
) -> None:
    if plan_key not in PLAN_CATALOG:
        raise ValueError("Unknown ClipKaro plan.")
    started = period_start or utc_now().isoformat()
    if not period_end:
        days = int(PLAN_CATALOG[plan_key].get("valid_days") or 31)
        period_end = (utc_now() + timedelta(days=days)).isoformat()
    await execute(
        """UPDATE users
           SET plan=?, billing_reference=?, plan_started_at=?, plan_expires_at=?, cancel_at_period_end=?, updated_at=?
           WHERE id=?""",
        (plan_key, reference, started, period_end, int(cancel_at_period_end), utc_now().isoformat(), user_id),
    )


async def downgrade_to_free(user_id: str) -> None:
    await execute(
        """UPDATE users SET plan='free', billing_reference=NULL, plan_started_at=NULL,
           plan_expires_at=NULL, cancel_at_period_end=0, updated_at=? WHERE id=?""",
        (utc_now().isoformat(), user_id),
    )


async def sync_subscription_if_needed(user: dict[str, Any], force: bool = False) -> dict[str, Any]:
    plan = str(user.get("plan") or "free")
    if plan not in SUBSCRIPTION_PLANS:
        expiry = parse_iso(user.get("plan_expires_at"))
        if plan == "mini_pass" and expiry and expiry <= utc_now():
            await downgrade_to_free(str(user["id"]))
            fresh = await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],))
            return fresh or user
        return user

    expiry = parse_iso(user.get("plan_expires_at"))
    if not force and expiry and expiry > utc_now():
        return user
    reference = str(user.get("billing_reference") or "")
    if not reference.startswith("sub_"):
        if expiry and expiry <= utc_now():
            await downgrade_to_free(str(user["id"]))
            return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user
        return user

    try:
        entity = await razorpay_request("GET", f"/subscriptions/{reference}")
    except RuntimeError:
        # Do not remove paid access merely because Razorpay is temporarily unreachable.
        return user

    status = str(entity.get("status") or "")
    start = iso_from_epoch(entity.get("current_start")) or user.get("plan_started_at")
    end = iso_from_epoch(entity.get("current_end")) or user.get("plan_expires_at")
    provider_plan_id = str(entity.get("plan_id") or "")
    expected = await fetch_one("SELECT plan_key FROM billing_plans WHERE provider_plan_id=?", (provider_plan_id,))
    # Provider notes are descriptive only and must never become entitlement
    # authority. If an older subscription is missing a local plan mapping, keep
    # the already-trusted local plan until the canonical billing lifecycle can
    # reconcile an explicit provider-plan binding.
    resolved_plan = str((expected or {}).get("plan_key") or plan)

    if status == "active" and resolved_plan in SUBSCRIPTION_PLANS:
        await activate_entitlement(
            str(user["id"]), resolved_plan, reference,
            period_start=start,
            period_end=end,
            # `has_scheduled_changes` also represents a scheduled downgrade; it
            # is not equivalent to cancellation. Preserve ClipKaro's explicit
            # cancellation flag, which is maintained by the lifecycle service.
            cancel_at_period_end=bool(user.get("cancel_at_period_end", 0)),
        )
    elif status in {"authenticated", "pending", "paused", "halted", "cancelled", "completed", "expired"}:
        # These states do not prove a newly paid period. Keep access only through
        # the already-known/provider-reported paid boundary. If that boundary has
        # passed, fail closed to Free; a later active/resumed webhook can restore
        # the subscription through its durable checkout binding.
        parsed_end = parse_iso(end)
        if parsed_end and parsed_end <= utc_now():
            await downgrade_to_free(str(user["id"]))

    return await fetch_one("SELECT * FROM users WHERE id=?", (user["id"],)) or user

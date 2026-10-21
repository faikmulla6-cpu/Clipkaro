"""Razorpay-backed, strictly server-priced creator allowance top-ups.

Credits are stored independently of immutable plan snapshots. A captured order
credits a wallet once, regardless of callback and webhook delivery order.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.database import distributed_advisory_lock, execute, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.billing import PLAN_CATALOG, razorpay_request, utc_now, verify_order_signature
from app.services.legal import checkout_allowed, has_current_legal_acceptance

router = APIRouter()
logger = logging.getLogger("clipkaro.topups")
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Use current catalog purchase caps, not grandfathered purchased-cycle limits.
PURCHASE_LIMITS = {"creator": (120, 15), "growth": (300, 50), "pro": (600, 150), "agency": (1500, 500)}
MINUTES_PAISE = 300
SHORT_PAISE = 200


def validate_quantities(plan: str, minutes: Any, shorts: Any) -> tuple[int, int, int]:
    if plan not in PURCHASE_LIMITS:
        raise HTTPException(403, "Extra credits are available on Creator, Growth, Pro and Agency plans. Choose a subscription first.")
    # bool is a subclass of int, but should never be accepted as a quantity.
    if type(minutes) is not int or type(shorts) is not int:
        raise HTTPException(422, "Choose whole-number quantities only.")
    maximum_minutes, maximum_shorts = PURCHASE_LIMITS[plan]
    if minutes < 0 or (minutes and not 10 <= minutes <= maximum_minutes):
        raise HTTPException(422, f"Karo Minutes: select 0 or 10–{maximum_minutes} minutes.")
    if shorts < 0 or shorts > maximum_shorts:
        raise HTTPException(422, f"AI Shorts: select 0–{maximum_shorts} credits.")
    if minutes == 0 and shorts == 0:
        raise HTTPException(422, "Choose Karo Minutes, AI Shorts, or both.")
    return minutes, shorts, minutes * MINUTES_PAISE + shorts * SHORT_PAISE


def payment_matches(payment: dict[str, Any], checkout: dict[str, Any], payment_id: str) -> tuple[bool, bool]:
    exact = bool(
        str(payment.get("id") or "") == payment_id
        and str(payment.get("order_id") or "") == str(checkout["provider_reference"])
        and type(payment.get("amount")) is int
        and payment["amount"] == int(checkout["amount_paise"])
        and str(payment.get("currency") or "").upper() == "INR"
    )
    return exact, bool(exact and payment.get("status") == "captured" and payment.get("captured", True))


async def balance_for(user_id: str) -> tuple[float, int]:
    row = await fetch_one("SELECT minutes_balance,shorts_balance FROM credit_topup_wallets WHERE user_id=?", (user_id,))
    return max(0.0, float((row or {}).get("minutes_balance") or 0)), max(0, int((row or {}).get("shorts_balance") or 0))


async def credit_checkout(checkout_id: str, payment_id: str | None = None) -> tuple[bool, float, int]:
    async def transaction(db) -> tuple[bool, float, int]:
        cur = await db.execute("SELECT * FROM credit_topup_checkouts WHERE id=?", (checkout_id,))
        row = await cur.fetchone()
        if not row:
            raise ValueError("Missing allowance checkout")
        checkout = dict(row)
        user_id = str(checkout["user_id"])
        now = utc_now().isoformat()
        # The conditional UPDATE is the settlement's database-level claim.
        # A plain SELECT followed by a wallet increment is unsafe in PostgreSQL:
        # two webhook/callback transactions may both read 'created' before either
        # obtains the wallet row lock. PostgreSQL rechecks this UPDATE predicate
        # after waiting for the checkout row lock; only one caller wins.
        #
        # Claim and wallet mutation are in the SAME transaction: a failed wallet
        # update also rolls the checkout back to its previous status.
        cur = await db.execute(
            """UPDATE credit_topup_checkouts
               SET status='verified', payment_id=COALESCE(?,payment_id), verified_at=?
               WHERE id=? AND status!='verified'
               RETURNING id""",
            (payment_id, now, checkout_id),
        )
        claimed = await cur.fetchone() is not None
        if claimed:
            await db.execute(
                """INSERT INTO credit_topup_wallets(user_id,minutes_balance,shorts_balance,updated_at)
                   VALUES (?,0,0,?) ON CONFLICT(user_id) DO NOTHING""", (user_id, now)
            )
            await db.execute(
                """UPDATE credit_topup_wallets
                   SET minutes_balance=minutes_balance+?,shorts_balance=shorts_balance+?,updated_at=?
                   WHERE user_id=?""",
                (float(checkout["minutes"]), int(checkout["shorts"]), now, user_id),
            )
        cur = await db.execute("SELECT minutes_balance,shorts_balance FROM credit_topup_wallets WHERE user_id=?", (user_id,))
        wallet_row = await cur.fetchone()
        wallet = dict(wallet_row) if wallet_row else {"minutes_balance": 0.0, "shorts_balance": 0}
        return claimed, float(wallet["minutes_balance"]), int(wallet["shorts_balance"])

    return await run_in_transaction(transaction, mode="IMMEDIATE", operation_name="settle captured allowance purchase")


@router.get("/credits/quote")
async def quote(user: dict = Depends(current_user)) -> dict[str, Any]:
    limits = PURCHASE_LIMITS.get(str(user.get("plan")))
    wallet_minutes, wallet_shorts = await balance_for(str(user["id"]))
    return {
        "eligible": limits is not None,
        "minutes_max": limits[0] if limits else 0,
        "shorts_max": limits[1] if limits else 0,
        "minutes_min": 10,
        "minutes_paise": MINUTES_PAISE,
        "short_paise": SHORT_PAISE,
        "purchased_minutes_left": round(wallet_minutes, 4),
        "purchased_shorts_left": wallet_shorts,
    }


@router.post("/credits/checkout")
async def checkout(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    minutes, shorts, amount = validate_quantities(str(user.get("plan") or "free"), body.get("minutes"), body.get("shorts"))
    if not user.get("email"):
        raise HTTPException(403, "Add a verified email to your account before purchasing credits.")
    allowed, reason = checkout_allowed()
    if not allowed:
        raise HTTPException(403, reason)
    if not await has_current_legal_acceptance(str(user["id"])):
        raise HTTPException(403, "Accept the current Terms, Privacy Notice and Refund Policy in Plans & billing before purchasing credits.")
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(503, "Razorpay payments are temporarily unavailable. Please try later.")
    user_id = str(user["id"])
    async with _locks[user_id], distributed_advisory_lock(f"credits-checkout:{user_id}"):
        cutoff = (utc_now() - timedelta(minutes=15)).isoformat()
        await execute(
            """UPDATE credit_topup_checkouts SET status='expired'
               WHERE user_id=? AND minutes=? AND shorts=? AND status='created' AND created_at<?""",
            (user_id, minutes, shorts, cutoff),
        )
        existing = await fetch_one(
            """SELECT * FROM credit_topup_checkouts
               WHERE user_id=? AND minutes=? AND shorts=? AND status IN ('created','authorized')
               ORDER BY created_at DESC LIMIT 1""", (user_id, minutes, shorts)
        )
        if existing:
            order_id = str(existing["provider_reference"])
        else:
            receipt = f"cktop_{user_id[:8]}_{uuid.uuid4().hex[:12]}"
            try:
                order = await razorpay_request("POST", "/orders", json_body={
                    "amount": amount, "currency": "INR", "receipt": receipt,
                    "notes": {"product": "ClipKaro creator credits", "purpose": "allowance_topup", "user_id": user_id},
                })
            except RuntimeError as exc:
                logger.warning("Razorpay top-up order creation failed type=%s", type(exc).__name__)
                raise HTTPException(502, "Could not start secure checkout. Please try again.") from exc
            order_id = str(order.get("id") or "")
            if not order_id.startswith("order_"):
                raise HTTPException(502, "Razorpay did not return a valid order.")
            await execute(
                """INSERT INTO credit_topup_checkouts
                   (id,user_id,provider_reference,minutes,shorts,amount_paise,status,created_at)
                   VALUES(?,?,?,?,?,?,'created',?)""",
                (str(uuid.uuid4()), user_id, order_id, minutes, shorts, amount, utc_now().isoformat()),
            )
    return {
        "key_id": settings.razorpay_key_id, "order_id": order_id,
        "amount": amount, "currency": "INR", "name": "ClipKaro AI",
        "description": f"{minutes} Karo Minutes + {shorts} AI Shorts",
        "prefill": {"name": user.get("name", ""), "email": user.get("email", "")},
    }


@router.post("/credits/verify")
async def verify(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    order_id = str(body.get("razorpay_order_id") or "")
    payment_id = str(body.get("razorpay_payment_id") or "")
    signature = str(body.get("razorpay_signature") or "")
    if not order_id or not payment_id or not signature:
        raise HTTPException(422, "Incomplete Razorpay payment confirmation.")
    row = await fetch_one("SELECT * FROM credit_topup_checkouts WHERE provider_reference=? AND user_id=?", (order_id, user["id"]))
    if not row:
        raise HTTPException(404, "Checkout not found for this account.")
    if not verify_order_signature(order_id, payment_id, signature):
        raise HTTPException(400, "Invalid payment signature.")
    # The signed webhook may have already settled this captured order. Returning
    # the persisted wallet avoids a false failure when the provider read is down.
    if row["status"] == "verified":
        minutes_balance, shorts_balance = await balance_for(str(user["id"]))
        return {"verified": True, "minutes_balance": minutes_balance, "shorts_balance": shorts_balance}
    try:
        payment = await razorpay_request("GET", f"/payments/{payment_id}")
    except RuntimeError as exc:
        raise HTTPException(502, "Payment received, but confirmation is delayed. Your balance will update automatically once Razorpay confirms it.") from exc
    identity, captured = payment_matches(payment, row, payment_id)
    if not identity:
        raise HTTPException(400, "Payment identity or amount did not match this order.")
    if not captured:
        await execute("UPDATE credit_topup_checkouts SET status='authorized',payment_id=? WHERE id=? AND status NOT IN ('verified','expired')", (payment_id, row["id"]))
        return {"verified": False, "pending": True}
    async with distributed_advisory_lock(f"credit-topup:{order_id}"):
        _, minutes_balance, shorts_balance = await credit_checkout(str(row["id"]), payment_id)
    return {"verified": True, "minutes_balance": minutes_balance, "shorts_balance": shorts_balance}


async def reconcile_credit_topup_webhook(event: str, payment: dict, order: dict) -> dict[str, Any] | None:
    reference = str(payment.get("order_id") or order.get("id") or "")
    if not reference:
        return None
    row = await fetch_one("SELECT * FROM credit_topup_checkouts WHERE provider_reference=?", (reference,))
    if not row:
        return None
    amount = int(row["amount_paise"])
    identity = False
    if event == "payment.captured":
        identity = (str(payment.get("order_id") or "") == reference and
                    str(payment.get("status") or "") == "captured" and
                    payment.get("amount") == amount and str(payment.get("currency") or "").upper() == "INR")
    elif event == "order.paid":
        identity = (str(order.get("id") or "") == reference and str(order.get("status") or "") == "paid" and
                    order.get("amount_paid") == amount and str(order.get("currency") or "").upper() == "INR" and
                    (not payment or (payment.get("status") == "captured" and payment.get("amount") == amount and payment.get("order_id") == reference)))
    if identity:
        async with distributed_advisory_lock(f"credit-topup:{reference}"):
            await credit_checkout(str(row["id"]), str(payment.get("id") or "") or None)
        return {"user_id": row["user_id"], "amount": amount, "status": "verified"}
    if event == "payment.authorized" and payment.get("order_id") == reference and payment.get("amount") == amount and str(payment.get("currency") or "").upper() == "INR" and payment.get("status") == "authorized":
        await execute("UPDATE credit_topup_checkouts SET status='authorized' WHERE id=? AND status='created'", (row["id"],))
        return {"user_id": row["user_id"], "amount": amount, "status": "authorized"}
    if event == "payment.failed" and payment.get("order_id") == reference and payment.get("amount") == amount and str(payment.get("currency") or "").upper() == "INR" and payment.get("status") == "failed":
        await execute("UPDATE credit_topup_checkouts SET status='failed' WHERE id=? AND status IN ('created','authorized')", (row["id"],))
        return {"user_id": row["user_id"], "amount": amount, "status": "failed"}
    # Do not credit on failed, mismatched, or unrecognized events.
    return {"user_id": row["user_id"], "amount": amount, "status": "ignored"}

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.database import POSTGRES_SCHEMA_REVISION, fetch_one, run_in_transaction
from app.services.billing import SUBSCRIPTION_PLANS, parse_iso, utc_now

CARTOON_SECONDS = {"free": 30, "mini_pass": 60, "creator": 300, "growth": 900, "pro": 1800, "agency": 3600}
REFILL_THRESHOLD_SECONDS = 30
REFILL_WAIT = timedelta(hours=24)


async def usage_schema_ready() -> bool:
    if get_settings().normalized_database_backend != "postgres":
        return True
    row = await fetch_one("SELECT version_num FROM alembic_version LIMIT 1")
    return bool(row and row["version_num"] == POSTGRES_SCHEMA_REVISION)


async def _account(db, user_id: str, *, lock: bool = False) -> dict:
    suffix = " FOR UPDATE" if lock and get_settings().normalized_database_backend == "postgres" else ""
    row = await (await db.execute(
        "SELECT id,plan,billing_reference,plan_started_at,plan_expires_at FROM users WHERE id=?" + suffix,
        (user_id,),
    )).fetchone()
    if not row:
        raise HTTPException(401, "Account not found.")
    return dict(row)


def _period(account: dict, now: datetime) -> tuple[str, str, datetime | None]:
    plan = account.get("plan")
    ends = parse_iso(account.get("plan_expires_at"))
    if plan not in CARTOON_SECONDS or plan == "free" or (ends and ends <= now):
        return "free", "free:lifetime", None
    started = parse_iso(account.get("plan_started_at"))
    reference = account.get("billing_reference") or account["id"]
    if plan == "mini_pass":
        purchase = account.get("billing_reference") or (started.isoformat() if started else account["id"])
        return plan, f"mini_pass:{purchase}", ends
    billing_cycle = started.astimezone(timezone.utc).isoformat() if started else now.strftime("%Y-%m")
    return plan, f"subscription:{reference}:{billing_cycle}", ends


async def _balance(db, account: dict, now: datetime) -> tuple[str, dict]:
    plan, period_key, ends = _period(account, now)
    allowance = CARTOON_SECONDS[plan]
    refill = await (await db.execute(
        "SELECT granted_seconds FROM cartoon_usage_refills WHERE user_id=? AND period_key=?",
        (account["id"], period_key),
    )).fetchone()
    projects = await (await db.execute(
        """SELECT duration_seconds,status,updated_at FROM cartoon_projects
           WHERE user_id=? AND usage_period_key=? AND status IN ('queued','processing','ready')
           ORDER BY updated_at,id""",
        (account["id"], period_key),
    )).fetchall()
    used = reserved = 0
    unlock = None
    finished_count = 0
    for row in projects:
        seconds, status, timestamp = row
        if status == "ready":
            used += int(seconds)
            finished_count += 1
            if plan in SUBSCRIPTION_PLANS and not refill and unlock is None and allowance - used <= REFILL_THRESHOLD_SECONDS:
                finished_at = parse_iso(timestamp)
                if finished_at:
                    unlock = finished_at + REFILL_WAIT
        else:
            reserved += int(seconds)
    granted = int(refill[0]) if refill else 0
    if unlock and ends and unlock >= ends:
        unlock = None
    balance = max(0, allowance + granted - used - reserved)
    if plan == "free" and (finished_count or reserved):
        balance = 0
    return period_key, {
        "plan": plan,
        "base_seconds": allowance,
        "remaining_seconds": balance,
        "used_seconds": used,
        "reserved_seconds": reserved,
        "refill_seconds": granted,
        "refill_available_at": unlock.isoformat() if unlock else None,
        "refill_claimable": bool(unlock and now >= unlock and (not ends or now < ends)),
        "refill_claimed": bool(refill),
        "period_ends_at": ends.isoformat() if ends else None,
    }


async def cartoon_balance(user_id: str) -> dict:
    async def read(db):
        _, balance = await _balance(db, await _account(db, user_id), utc_now())
        return balance

    return await run_in_transaction(read, mode="DEFERRED", operation_name="read cartoon balance")


async def reserve_cartoon_period(db, user_id: str, duration: int, *, metered: bool = True) -> str | None:
    account = await _account(db, user_id, lock=True)
    active = await (await db.execute(
        "SELECT id FROM cartoon_projects WHERE user_id=? AND status IN ('queued','processing') LIMIT 1",
        (user_id,),
    )).fetchone()
    if active:
        raise HTTPException(409, "You already have a cartoon rendering. Wait for it to finish.")
    if not metered:
        return None
    period, balance = await _balance(db, account, utc_now())
    if duration > balance["remaining_seconds"]:
        raise HTTPException(409, "This duration exceeds your available cartoon time. Choose a shorter duration or check your refill.")
    return period


async def claim_cartoon_refill(user_id: str) -> dict:
    async def claim(db):
        account = await _account(db, user_id, lock=True)
        now = utc_now()
        period, balance = await _balance(db, account, now)
        if balance["refill_claimed"]:
            return balance
        if not balance["refill_claimable"]:
            raise HTTPException(409, "Your cartoon refill is not available yet.")
        await db.execute(
            "INSERT INTO cartoon_usage_refills(user_id,period_key,granted_seconds,claimed_at) VALUES (?,?,?,?)",
            (user_id, period, balance["base_seconds"], now.isoformat()),
        )
        _, updated = await _balance(db, account, now)
        return updated

    return await run_in_transaction(claim, operation_name="claim cartoon refill")

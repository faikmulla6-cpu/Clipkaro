"""Isolated Real Smart Layout credits: one durable charge per source/range.

Never shares the Karo Minute, Short, or top-up wallet. Caller supplies only
authenticated user and DB-derived AnalysisIdentity. All mutations are atomic.
"""
from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.database import fetch_one, run_in_transaction
from app.services.billing import entitlement_for, mini_pass_is_exhausted, usage_period_key
from app.services.smart_layout_cache import AnalysisIdentity

POLICY_VERSION = "smart-layout-balanced-v2-free-once"
# Immutable lifetime entitlement; never use the monthly Free billing period here.
FREE_TRIAL_PERIOD_KEY = "free:smart-layout-once:v1"
LIMITS: dict[str, tuple[int, int]] = {
    "free": (1, 1),
    "mini_pass": (1, 1),
    "creator": (12, 4),
    "growth": (40, 10),
    "pro": (120, 25),
    "agency": (300, 60),
}
MAX_CREDITS_PER_CLIP = 3


class SmartLayoutQuotaError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def credit_cost(duration: float) -> int:
    if not math.isfinite(duration) or duration < .1 or duration > 180.:
        raise SmartLayoutQuotaError("SMART_LAYOUT_DURATION", "Smart Layout supports clips from 0.1 to 180 seconds.")
    # Identity rounds times to milliseconds or finer; avoid binary float
    # roundoff at exact minute boundaries without rounding up actual overage.
    return max(1, min(MAX_CREDITS_PER_CLIP, math.ceil((round(duration, 4) - .00000001) / 60.)))


def analysis_fingerprint(identity: AnalysisIdentity) -> str:
    item = identity.validated()
    # Deliberately omit analyzer/model revision and plan/billing period:
    # changing a model or expiring the private result must not charge again.
    raw = "|".join((item.user_id, item.video_id, item.generation,
                    f"{item.start:.4f}", f"{item.end:.4f}"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_plan(user: dict, now: datetime) -> str:
    plan = str(user.get("plan") or "free")
    if plan not in LIMITS or plan == "free":
        return "free"
    expiry = str(user.get("plan_expires_at") or "")
    if not expiry:
        return "free"  # Never trust an unverified paid period.
    try:
        end = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end <= now:
            return "free"
    except ValueError:
        return "free"
    return plan


def _period_end(user: dict) -> str | None:
    return str(user.get("plan_expires_at") or "") or None


def _smart_period(user: dict, plan: str) -> str:
    # Every Free account gets exactly one lifetime trial, never a new monthly grant.
    # Paid period keys and grandfathered credits remain unchanged.
    return FREE_TRIAL_PERIOD_KEY if plan == "free" else usage_period_key(user)


async def init_smart_layout_credits() -> None:
    """Local SQLite uses lazy dev schema; production uses Alembic revision 12."""
    if get_settings().normalized_database_backend == "postgres":
        return
    async def setup(db) -> None:
        await db.execute("""CREATE TABLE IF NOT EXISTS smart_layout_credit_periods(
            user_id TEXT NOT NULL, period_key TEXT NOT NULL, plan_key TEXT NOT NULL,
            allowance INTEGER NOT NULL, daily_cap INTEGER NOT NULL,
            policy_version TEXT NOT NULL, period_end TEXT, created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, period_key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS smart_layout_credit_reservations(
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            period_key TEXT NOT NULL, credits INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('reserved','finalized','released')),
            job_id TEXT, reserved_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(user_id,fingerprint),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_smart_credit_period ON smart_layout_credit_reservations(user_id,period_key,status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_smart_credit_daily ON smart_layout_credit_reservations(user_id,reserved_at,status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_smart_credit_job ON smart_layout_credit_reservations(job_id)")
    await run_in_transaction(setup, operation_name="init Smart Layout credits")


async def _mini_pass_exhausted_locked(db, user: dict) -> bool:
    """Enforce the original purchased Mini Pass rights under its user lock.

    A Smart Layout credit cannot extend the one-time pass beyond its source
    minute pool or its Short creation allowance. entitlement_for() prepares
    the immutable purchased snapshot BEFORE this transaction, so the check
    reads the same grants as ClipKaro's media and Short billing triggers.
    """
    if str(user.get("plan") or "") != "mini_pass":
        return False
    uid = str(user["id"])
    period = usage_period_key(user)
    snapshot = await (await db.execute(
        """SELECT shorts,processing_minutes,short_mode FROM plan_entitlement_snapshots
           WHERE user_id=? AND period_key=?""", (uid,period))).fetchone()
    if not snapshot:
        # Never assume an unverified paid grant exists.
        raise SmartLayoutQuotaError(
            "SMART_LAYOUT_PASS_UNVERIFIED", "Mini Pass entitlement is not ready. Please retry.")
    if str(snapshot["short_mode"]) == "finished_shorts":
        counted = await (await db.execute(
            """SELECT COUNT(*) AS n FROM short_credit_reservations
               WHERE user_id=? AND period_key=? AND status IN ('reserved','finalized')""",
            (uid,period))).fetchone()
    else:
        counted = await (await db.execute(
            """SELECT COUNT(DISTINCT resource_id) AS n FROM usage_reservations
               WHERE user_id=? AND period_key=? AND kind='minutes'
                 AND status IN ('reserved','finalized')""", (uid,period))).fetchone()
    minutes = await (await db.execute(
        "SELECT source_minutes FROM usage WHERE user_id=? AND month=?",
        (uid,period))).fetchone()
    used_shorts = int(counted["n"] if counted else 0)
    used_minutes = float(minutes["source_minutes"] if minutes else 0)
    return (used_shorts >= int(snapshot["shorts"])
            or used_minutes >= float(snapshot["processing_minutes"]) - .001)


async def _release_terminal_failures(db, uid: str, now: datetime) -> None:
    """Repair interrupted refunds, but never release active/requeued work."""
    await db.execute(
        """UPDATE smart_layout_credit_reservations
           SET status='released',updated_at=?
           WHERE user_id=? AND status='reserved' AND job_id IN
             (SELECT id FROM jobs WHERE user_id=?
                AND kind='smart_layout_analysis' AND status='failed')""",
        (now.isoformat(),uid,uid))


async def _balance(db, uid: str, period: str, cap: int, daily: int, now: datetime) -> dict:
    row = await (await db.execute(
        """SELECT COALESCE(SUM(credits),0) used FROM smart_layout_credit_reservations
           WHERE user_id=? AND period_key=? AND status IN ('reserved','finalized')""",
        (uid, period))).fetchone()
    used = int(row["used"] if row else 0)
    if period == FREE_TRIAL_PERIOD_KEY:
        # Trial is lifetime-limited, not a rolling 24h grant. Paid usage today
        # must not unexpectedly consume the separate trial entitlement.
        return {
            "allowance": cap, "used": used, "remaining": max(0, cap-used),
            "daily_cap": daily, "daily_used": used,
            "daily_remaining": max(0, daily-used),
        }
    since = (now - timedelta(hours=24)).isoformat()
    row = await (await db.execute(
        """SELECT COALESCE(SUM(credits),0) used FROM smart_layout_credit_reservations
           WHERE user_id=? AND status IN ('reserved','finalized') AND reserved_at>=?""",
        (uid, since))).fetchone()
    daily_used = int(row["used"] if row else 0)
    return {
        "allowance": cap, "used": used, "remaining": max(0, cap-used),
        "daily_cap": daily, "daily_used": daily_used,
        "daily_remaining": max(0, daily-daily_used),
    }


async def entitlement_status(user: dict, *, rollout: bool) -> dict:
    """Customer-safe balance. Reconciles only verified terminal failed jobs."""
    now = _now()
    uid = str(user["id"])
    current = await fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    if not current:
        raise SmartLayoutQuotaError("SMART_LAYOUT_AUTH", "Account unavailable.")
    plan = _active_plan(current, now)
    mini_exhausted = plan == "mini_pass" and await mini_pass_is_exhausted(current)
    allowance, daily = LIMITS[plan]
    period = _smart_period(current, plan)
    async def check(db):
        await _release_terminal_failures(db, uid, now)
        snapshot = await (await db.execute(
            """SELECT plan_key,allowance,daily_cap
               FROM smart_layout_credit_periods WHERE user_id=? AND period_key=?""",
            (uid,period))).fetchone()
        effective_allowance, effective_daily = allowance, daily
        if snapshot and snapshot["plan_key"] == plan:
            effective_allowance = int(snapshot["allowance"])
            effective_daily = int(snapshot["daily_cap"])
        return await _balance(db, uid, period, effective_allowance, effective_daily, now)
    balance = await run_in_transaction(check, operation_name="read Smart Layout balance")
    return {
        **balance, "plan": plan, "enabled": bool(rollout and allowance and not mini_exhausted),
        "pass_exhausted": bool(mini_exhausted),
        "rollout_enabled": bool(rollout), "policy_version": POLICY_VERSION,
        "period_end": _period_end(current) if plan != "free" else None,
    }


async def previously_paid(identity: AnalysisIdentity) -> bool:
    """An authenticated exact source/range may be reanalyzed free after TTL.

    Ownership is verified by the calling API's _owned() source query.
    No model revision or cache expiration can mint a duplicate charge.
    """
    item = identity.validated()
    row = await fetch_one(
        """SELECT 1 AS paid FROM smart_layout_credit_reservations
           WHERE user_id=? AND fingerprint=? AND status='finalized'""",
        (item.user_id, analysis_fingerprint(item)),
    )
    return bool(row)


async def reserve_analysis(user_id: str, identity: AnalysisIdentity) -> tuple[str, str]:
    """Atomically reserve credits and create one durable job+payload.

    Return (job_id, action): 'new_charge', 'free_refresh', or 'existing'.
    Uses PostgreSQL user-row FOR UPDATE to serialize DIFFERENT clip requests,
    while the unique fingerprint serializes identical requests and retries.
    """
    identity = identity.validated()
    uid = str(user_id)
    if uid != identity.user_id:
        raise SmartLayoutQuotaError("SMART_LAYOUT_OWNER", "Source ownership mismatch.")
    now = _now()
    timestamp = now.isoformat()
    fingerprint = analysis_fingerprint(identity)
    requested_cost = credit_cost(identity.end - identity.start)
    # Initialize the purchased pass snapshot outside the reservation lock.
    # The authoritative exhaustion check then runs inside the same lock
    # and transaction as the Smart Layout credit reservation.
    preflight = await fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    if preflight and str(preflight.get("plan") or "") == "mini_pass":
        await entitlement_for(preflight)
    from app.services.smart_layout_cache import private_plan_key
    import json

    async def reserve(db):
        locking = (" FOR UPDATE" if get_settings().normalized_database_backend == "postgres" else "")
        user = await (await db.execute(
            "SELECT * FROM users WHERE id=?" + locking, (uid,))).fetchone()
        if not user:
            raise SmartLayoutQuotaError("SMART_LAYOUT_AUTH", "Account unavailable.")
        owned = dict(user)
        plan = _active_plan(owned, now)
        cap, daily = LIMITS[plan]
        cost = 1 if plan == "free" else requested_cost
        if not cap:
            raise SmartLayoutQuotaError("SMART_LAYOUT_UPGRADE", "Real Smart Layout requires an active premium plan or available Free trial.")
        if plan == "mini_pass" and await _mini_pass_exhausted_locked(db, owned):
            raise SmartLayoutQuotaError(
                "SMART_LAYOUT_PASS_EXHAUSTED", "This Mini Pass has reached its existing creation or minute allowance.")
        period = _smart_period(owned, plan)
        await _release_terminal_failures(db, uid, now)
        snapshot = await (await db.execute(
            """SELECT plan_key,allowance,daily_cap
               FROM smart_layout_credit_periods WHERE user_id=? AND period_key=?""",
            (uid,period))).fetchone()
        if snapshot and snapshot["plan_key"] == plan:
            # Honor the original purchased period policy. A future increase
            # or reduction cannot rewrite previously granted credits.
            cap,daily = int(snapshot["allowance"]),int(snapshot["daily_cap"])
        existing = await (await db.execute(
            """SELECT status,job_id FROM smart_layout_credit_reservations
               WHERE user_id=? AND fingerprint=?""", (uid,fingerprint))).fetchone()
        if existing and existing["status"] == "reserved":
            job = await (await db.execute(
                "SELECT status FROM jobs WHERE id=?", (existing["job_id"],))).fetchone()
            if job and job["status"] in ("queued", "processing"):
                return str(existing["job_id"]), "existing"
            # A verified terminal failure releases only the stale reservation.
            if job and job["status"] == "failed":
                await db.execute(
                    """UPDATE smart_layout_credit_reservations
                       SET status='released',updated_at=?
                       WHERE user_id=? AND fingerprint=? AND status='reserved'""",
                    (timestamp,uid,fingerprint))
            else:
                # An unconfirmed state is never recharged or redispatched.
                raise SmartLayoutQuotaError("SMART_LAYOUT_PENDING", "Previous analysis is being recovered. Try again shortly.")
        # Existing finalized analysis may be recomputed at zero cost when its
        # private plan TTL or model revision changes.
        free_recompute = bool(existing and existing["status"] == "finalized")
        if free_recompute and plan == "free":
            # Free preview is truly once; a TTL/model refresh cannot mint
            # more background analysis after the first successful trial.
            raise SmartLayoutQuotaError(
                "SMART_LAYOUT_TRIAL_EXHAUSTED", "Your one-time free Smart Layout preview has been used.")
        balance = await _balance(db, uid, period, cap, daily, now)
        if not free_recompute and balance["remaining"] < cost:
            raise SmartLayoutQuotaError("SMART_LAYOUT_CREDITS", "Not enough Smart Layout credits for this clip.")
        if not free_recompute and balance["daily_remaining"] < cost:
            raise SmartLayoutQuotaError("SMART_LAYOUT_DAILY", "Your Smart Layout daily credit allowance is reached.")
        active = await (await db.execute(
            """SELECT COUNT(*) AS n FROM jobs
               WHERE user_id=? AND kind='smart_layout_analysis'
                 AND status IN ('queued','processing')""", (uid,))).fetchone()
        if int(active["n"] if active else 0) >= 2:
            raise SmartLayoutQuotaError("SMART_LAYOUT_CONCURRENCY", "Two previews are already being analyzed.")
        # Record a purchased-period snapshot once, rather than mutating other
        # billing snapshots or any preexisting Short/minute entitlements.
        await db.execute(
            """INSERT INTO smart_layout_credit_periods(
               user_id,period_key,plan_key,allowance,daily_cap,policy_version,period_end,created_at
               ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id,period_key) DO NOTHING""",
            (uid,period,plan,cap,daily,POLICY_VERSION,_period_end(owned),timestamp))
        job_id = str(uuid.uuid4())
        payload = json.dumps({"clip_id":identity.clip_id,
                              "cache_key":private_plan_key(identity)},separators=(",",":"))
        await db.execute(
            """INSERT INTO jobs(id,user_id,project_id,export_id,kind,status,progress,
                stage,message,error,created_at,updated_at)
               VALUES(?,?,?,NULL,'smart_layout_analysis','queued',0,
                'queued','Waiting to analyze',NULL,?,?)""",
            (job_id,uid,identity.project_id,timestamp,timestamp))
        await db.execute(
            """INSERT INTO job_payloads(job_id,payload_json,created_at,updated_at)
               VALUES (?,?,?,?)""", (job_id,payload,timestamp,timestamp))
        if free_recompute:
            # Preserve the ORIGINAL paid period, timestamp and finalized
            # credit. A cache miss cannot consume a later billing cycle.
            await db.execute(
                """UPDATE smart_layout_credit_reservations
                   SET job_id=?,updated_at=?
                   WHERE user_id=? AND fingerprint=? AND status='finalized'""",
                (job_id,timestamp,uid,fingerprint))
        elif existing:
            await db.execute(
                """UPDATE smart_layout_credit_reservations SET period_key=?,
                   credits=?,status='reserved',job_id=?,reserved_at=?,updated_at=?
                   WHERE user_id=? AND fingerprint=? AND status='released'""",
                (period,cost,job_id,timestamp,timestamp,uid,fingerprint))
        else:
            await db.execute(
                """INSERT INTO smart_layout_credit_reservations(
                  id,user_id,fingerprint,period_key,credits,status,job_id,reserved_at,updated_at)
                  VALUES(?,?,?,?,?,'reserved',?,?,?)""",
                (str(uuid.uuid4()),uid,fingerprint,period,cost,job_id,timestamp,timestamp))
        return job_id, "free_refresh" if free_recompute else "new_charge"

    return await run_in_transaction(reserve, operation_name="reserve Smart Layout credits and job")


async def finalize_verified_plan(job_id: str, user_id: str,
                                 identity: AnalysisIdentity, record: dict,
                                 *, source_expires_at: str | None) -> None:
    """Atomically publish validated preview geometry AND finalize its charge.

    Avoid a reusable cached plan with unbilled reserved/released credits if
    media workers crash, DB writes fail, or a forged job ID is presented.
    Validation and source ownership are performed by the calling worker.
    """
    identity = identity.validated()
    if user_id != identity.user_id:
        raise SmartLayoutQuotaError("SMART_LAYOUT_OWNER", "Paid analysis source owner changed.")
    from app.services.smart_layout_repository import store_plan

    async def publish(db):
        paid = await (await db.execute(
            """SELECT status FROM smart_layout_credit_reservations
               WHERE job_id=? AND user_id=? AND fingerprint=?""",
            (job_id,user_id,analysis_fingerprint(identity)),
        )).fetchone()
        if not paid or paid["status"] not in ("reserved", "finalized"):
            raise SmartLayoutQuotaError(
                "SMART_LAYOUT_RESERVATION", "Verified analysis cannot be published without paid entitlement.")
        await store_plan(identity, record, source_expires_at=source_expires_at,
                         transaction_db=db)
        if paid["status"] == "reserved":
            await db.execute(
                """UPDATE smart_layout_credit_reservations
                   SET status='finalized',updated_at=?
                   WHERE job_id=? AND user_id=? AND status='reserved'""",
                (_now().isoformat(),job_id,user_id),
            )
    await run_in_transaction(publish, operation_name="publish and settle Smart Layout analysis")


async def settle_analysis_job(job_id: str, *, succeeded: bool) -> None:
    """Idempotent settlement; caller marks success only AFTER private plan save."""
    timestamp = _now().isoformat()
    async def settle(db):
        await db.execute(
            """UPDATE smart_layout_credit_reservations
               SET status=?,updated_at=? WHERE job_id=? AND status='reserved'""",
            ("finalized" if succeeded else "released",timestamp,job_id))
    await run_in_transaction(settle, operation_name="settle Smart Layout analysis")


async def migrate_smart_layout_period(db, uid: str, old_period: str,
                                     new_period: str, target_plan: str) -> None:
    """Same-cycle upgrades preserve used/reserved credits and daily history."""
    cap,daily = LIMITS[target_plan]
    await db.execute(
        """UPDATE smart_layout_credit_reservations SET period_key=?
           WHERE user_id=? AND period_key=?""", (new_period,uid,old_period))
    await db.execute(
        """INSERT INTO smart_layout_credit_periods(
          user_id,period_key,plan_key,allowance,daily_cap,policy_version,created_at)
          VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(user_id,period_key) DO UPDATE SET
             plan_key=excluded.plan_key,allowance=excluded.allowance,
             daily_cap=excluded.daily_cap,policy_version=excluded.policy_version""",
        (uid,new_period,target_plan,cap,daily,POLICY_VERSION,_now().isoformat()))

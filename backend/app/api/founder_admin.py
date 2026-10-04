from __future__ import annotations

import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.database import fetch_all, fetch_one
from app.services.billing import PLAN_CATALOG, SUBSCRIPTION_PLANS


router = APIRouter(prefix="/admin", tags=["founder-admin"])
logger = logging.getLogger("clipkaro.founder_admin")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_SENSITIVE_METADATA_KEYS = {
    "password",
    "password_hash",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "payload_json",
    "webhook_secret",
    "razorpay_key_secret",
}
_SENSITIVE_METADATA_KEY_MARKERS = ("password", "token", "secret", "authorization", "cookie", "api_key", "apikey", "payload")
_CREDENTIAL_VALUE_PATTERNS = (
    re.compile(r"\brzp_live_[A-Za-z0-9]{8,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*"),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _admin_api_enabled() -> bool:
    return str(os.environ.get("ADMIN_API_ENABLED", "")).strip().lower() in _TRUE_VALUES


def _configured_service_token() -> str:
    return str(os.environ.get("ADMIN_API_SERVICE_TOKEN", "")).strip()


def _service_token_is_strong(token: str) -> bool:
    lowered = token.lower()
    if len(token) < 48:
        return False
    if any(marker in lowered for marker in ("replace", "placeholder", "changeme", "change-me", "required")):
        return False
    return len(set(token)) >= 16


async def require_founder_admin_service(authorization: str | None = Header(default=None)) -> None:
    """Authorize the private server-to-server Founder Console connection.

    This deliberately does not reuse customer ``current_user`` authentication.
    Customer auth may perform entitlement reconciliation, while every Stage 2C
    endpoint must remain database-read-only. The surface is hidden unless it is
    explicitly enabled, and a weak/missing configured token fails closed.
    """
    if not _admin_api_enabled():
        raise HTTPException(404, "Not found.")

    expected = _configured_service_token()
    if not _service_token_is_strong(expected):
        logger.error("Founder admin API enabled without a strong service token")
        raise HTTPException(503, "Founder admin API is unavailable.")

    scheme, _, supplied = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            401,
            "Founder admin service authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _bounded_limit(value: int) -> int:
    return max(1, min(int(value), 100))


def _bounded_offset(value: int) -> int:
    return max(0, min(int(value), 10000))


def _text(value: Any, *, maximum: int = 500) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return cleaned[:maximum]


def _sanitize_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9_]+", "_", str(key).strip().lower())
            if normalized in _SENSITIVE_METADATA_KEYS or any(marker in normalized for marker in _SENSITIVE_METADATA_KEY_MARKERS):
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = _sanitize_metadata(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_sanitize_metadata(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, str):
        cleaned = value[:1000]
        if any(pattern.search(cleaned) for pattern in _CREDENTIAL_VALUE_PATTERNS):
            return "[redacted]"
        return cleaned
    return value


def _audit_metadata(raw: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"status": "unreadable"}
    sanitized = _sanitize_metadata(parsed)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


async def _count(query: str, params: tuple[Any, ...] = ()) -> int:
    row = await fetch_one(query, params)
    return int((row or {}).get("count") or 0)


def _safe_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "email": row.get("email"),
        "plan": row.get("plan"),
        "role": row.get("role"),
        "onboarding_complete": bool(row.get("onboarding_complete", 0)),
        "email_verified": bool(row.get("email_verified_at")),
        "plan_started_at": row.get("plan_started_at"),
        "plan_expires_at": row.get("plan_expires_at"),
        "cancel_at_period_end": bool(row.get("cancel_at_period_end", 0)),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("/overview", dependencies=[Depends(require_founder_admin_service)])
async def admin_overview() -> dict[str, Any]:
    now = _utc_now()
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()

    verified_revenue = await fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS amount FROM billing_checkouts WHERE status='verified'"
    )
    verified_revenue_30d = await fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS amount FROM billing_checkouts WHERE status='verified' AND COALESCE(verified_at,created_at)>=?",
        (cutoff_30d,),
    )

    return {
        "generated_at": now.isoformat(),
        "mode": "read_only",
        "users": {
            "total": await _count("SELECT COUNT(*) AS count FROM users"),
            "created_24h": await _count("SELECT COUNT(*) AS count FROM users WHERE created_at>=?", (cutoff_24h,)),
            "paid_local_entitlements": await _count("SELECT COUNT(*) AS count FROM users WHERE plan<>'free'"),
        },
        "projects": {
            "total": await _count("SELECT COUNT(*) AS count FROM projects"),
            "created_24h": await _count("SELECT COUNT(*) AS count FROM projects WHERE created_at>=?", (cutoff_24h,)),
        },
        "jobs": {
            "queued": await _count("SELECT COUNT(*) AS count FROM jobs WHERE status='queued'"),
            "processing": await _count("SELECT COUNT(*) AS count FROM jobs WHERE status='processing'"),
            "completed_24h": await _count("SELECT COUNT(*) AS count FROM jobs WHERE status='completed' AND updated_at>=?", (cutoff_24h,)),
            "failed_24h": await _count("SELECT COUNT(*) AS count FROM jobs WHERE status='failed' AND updated_at>=?", (cutoff_24h,)),
        },
        "exports": {
            "ready_24h": await _count("SELECT COUNT(*) AS count FROM exports WHERE status='ready' AND created_at>=?", (cutoff_24h,)),
            "failed_24h": await _count("SELECT COUNT(*) AS count FROM exports WHERE status='failed' AND created_at>=?", (cutoff_24h,)),
        },
        "billing": {
            "verified_revenue_paise": int((verified_revenue or {}).get("amount") or 0),
            "verified_revenue_30d_paise": int((verified_revenue_30d or {}).get("amount") or 0),
            "currency": "INR",
            "source": "local_verified_checkouts",
        },
    }


@router.get("/users", dependencies=[Depends(require_founder_admin_service)])
async def admin_users(
    query: str = Query(default="", max_length=120),
    plan: str = Query(default="", max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    search = query.strip().lower()
    if search:
        clauses.append("(LOWER(id) LIKE ? OR LOWER(name) LIKE ? OR LOWER(email) LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])
    selected_plan = plan.strip().lower()
    if selected_plan:
        clauses.append("plan=?")
        params.append(selected_plan)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    total = await _count(f"SELECT COUNT(*) AS count FROM users{where}", tuple(params))
    rows = await fetch_all(
        f"""SELECT id,name,email,plan,role,onboarding_complete,email_verified_at,
                   plan_started_at,plan_expires_at,cancel_at_period_end,created_at,updated_at
            FROM users{where}
            ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?""",
        tuple([*params, _bounded_limit(limit), _bounded_offset(offset)]),
    )
    return {
        "items": [_safe_user(row) for row in rows],
        "pagination": {"total": total, "limit": _bounded_limit(limit), "offset": _bounded_offset(offset)},
    }


@router.get("/users/{user_id}", dependencies=[Depends(require_founder_admin_service)])
async def admin_user_detail(user_id: str) -> dict[str, Any]:
    row = await fetch_one(
        """SELECT id,name,email,plan,role,onboarding_complete,email_verified_at,
                  plan_started_at,plan_expires_at,cancel_at_period_end,created_at,updated_at
           FROM users WHERE id=?""",
        (user_id,),
    )
    if not row:
        raise HTTPException(404, "User not found.")

    counts = {
        "projects": await _count("SELECT COUNT(*) AS count FROM projects WHERE user_id=?", (user_id,)),
        "exports": await _count("SELECT COUNT(*) AS count FROM exports WHERE user_id=?", (user_id,)),
        "jobs": await _count("SELECT COUNT(*) AS count FROM jobs WHERE user_id=?", (user_id,)),
        "failed_jobs": await _count("SELECT COUNT(*) AS count FROM jobs WHERE user_id=? AND status='failed'", (user_id,)),
    }
    usage_rows = await fetch_all(
        """SELECT month,source_minutes,exports_used,exports_limit
           FROM usage WHERE user_id=? ORDER BY month DESC LIMIT 12""",
        (user_id,),
    )
    recent_projects = await fetch_all(
        """SELECT id,title,status,progress,stage,language,category,error,created_at,updated_at
           FROM projects WHERE user_id=? ORDER BY updated_at DESC LIMIT 10""",
        (user_id,),
    )
    recent_jobs = await fetch_all(
        """SELECT id,project_id,export_id,kind,status,progress,stage,message,error,created_at,updated_at
           FROM jobs WHERE user_id=? ORDER BY updated_at DESC LIMIT 10""",
        (user_id,),
    )
    for job in recent_jobs:
        job["message"] = _text(job.get("message"), maximum=300)
        job["error"] = _text(job.get("error"), maximum=500)

    return {
        "user": _safe_user(row),
        "counts": counts,
        "usage_periods": usage_rows,
        "recent_projects": recent_projects,
        "recent_jobs": recent_jobs,
    }


@router.get("/projects", dependencies=[Depends(require_founder_admin_service)])
async def admin_projects(
    status: str = Query(default="", max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    selected_status = status.strip().lower()
    where = " WHERE p.status=?" if selected_status else ""
    params: tuple[Any, ...] = (selected_status,) if selected_status else ()
    total = await _count(f"SELECT COUNT(*) AS count FROM projects p{where}", params)
    rows = await fetch_all(
        f"""SELECT p.id,p.user_id,u.email AS user_email,p.title,p.status,p.progress,p.stage,
                   p.language,p.category,p.error,p.created_at,p.updated_at
            FROM projects p JOIN users u ON u.id=p.user_id{where}
            ORDER BY p.updated_at DESC,p.id DESC LIMIT ? OFFSET ?""",
        tuple([*params, _bounded_limit(limit), _bounded_offset(offset)]),
    )
    for row in rows:
        row["error"] = _text(row.get("error"), maximum=500)
    return {
        "items": rows,
        "pagination": {"total": total, "limit": _bounded_limit(limit), "offset": _bounded_offset(offset)},
    }


@router.get("/jobs", dependencies=[Depends(require_founder_admin_service)])
async def admin_jobs(
    status: str = Query(default="", max_length=40),
    kind: str = Query(default="", max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    selected_status = status.strip().lower()
    selected_kind = kind.strip().lower()
    if selected_status:
        clauses.append("j.status=?")
        params.append(selected_status)
    if selected_kind:
        clauses.append("j.kind=?")
        params.append(selected_kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    total = await _count(f"SELECT COUNT(*) AS count FROM jobs j{where}", tuple(params))
    rows = await fetch_all(
        f"""SELECT j.id,j.user_id,u.email AS user_email,j.project_id,j.export_id,j.kind,j.status,
                   j.progress,j.stage,j.message,j.error,j.created_at,j.updated_at
            FROM jobs j JOIN users u ON u.id=j.user_id{where}
            ORDER BY j.updated_at DESC,j.id DESC LIMIT ? OFFSET ?""",
        tuple([*params, _bounded_limit(limit), _bounded_offset(offset)]),
    )
    for row in rows:
        row["message"] = _text(row.get("message"), maximum=300)
        row["error"] = _text(row.get("error"), maximum=500)
    return {
        "items": rows,
        "pagination": {"total": total, "limit": _bounded_limit(limit), "offset": _bounded_offset(offset)},
    }


@router.get("/billing/summary", dependencies=[Depends(require_founder_admin_service)])
async def admin_billing_summary() -> dict[str, Any]:
    cutoff_30d = (_utc_now() - timedelta(days=30)).isoformat()
    verified_all = await fetch_one(
        "SELECT COALESCE(SUM(amount),0) AS amount,COUNT(*) AS count FROM billing_checkouts WHERE status='verified'"
    )
    verified_30d = await fetch_one(
        """SELECT COALESCE(SUM(amount),0) AS amount,COUNT(*) AS count
           FROM billing_checkouts WHERE status='verified' AND COALESCE(verified_at,created_at)>=?""",
        (cutoff_30d,),
    )
    plan_rows = await fetch_all(
        "SELECT plan,COUNT(*) AS count FROM users GROUP BY plan ORDER BY count DESC,plan ASC"
    )
    failed_payments_30d = await _count(
        "SELECT COUNT(*) AS count FROM payment_events WHERE event_type='payment.failed' AND created_at>=?",
        (cutoff_30d,),
    )
    scheduled_cancellations = await _count(
        "SELECT COUNT(*) AS count FROM users WHERE cancel_at_period_end=1"
    )

    estimated_mrr_paise = 0
    for item in plan_rows:
        plan = str(item.get("plan") or "")
        if plan in SUBSCRIPTION_PLANS:
            estimated_mrr_paise += int((PLAN_CATALOG.get(plan) or {}).get("price_paise") or 0) * int(item.get("count") or 0)

    return {
        "currency": "INR",
        "verified_revenue": {
            "all_time_paise": int((verified_all or {}).get("amount") or 0),
            "all_time_checkouts": int((verified_all or {}).get("count") or 0),
            "last_30d_paise": int((verified_30d or {}).get("amount") or 0),
            "last_30d_checkouts": int((verified_30d or {}).get("count") or 0),
            "source": "local_verified_checkouts",
        },
        "estimated_local_mrr_paise": estimated_mrr_paise,
        "estimated_mrr_note": "Derived from current local recurring-plan entitlements; no live Razorpay reconciliation is performed by this read-only endpoint.",
        "plan_distribution": [{"plan": row.get("plan"), "count": int(row.get("count") or 0)} for row in plan_rows],
        "scheduled_cancellations": scheduled_cancellations,
        "failed_payment_events_30d": failed_payments_30d,
    }


@router.get("/usage", dependencies=[Depends(require_founder_admin_service)])
async def admin_usage_summary() -> dict[str, Any]:
    totals = await fetch_one(
        """SELECT COALESCE(SUM(source_minutes),0) AS source_minutes,
                  COALESCE(SUM(exports_used),0) AS exports_used,COUNT(*) AS periods
           FROM usage"""
    )
    reservations = await fetch_all(
        """SELECT kind,status,COUNT(*) AS count,COALESCE(SUM(amount),0) AS amount
           FROM usage_reservations GROUP BY kind,status ORDER BY kind,status"""
    )
    return {
        "recorded_usage": {
            "source_minutes": round(float((totals or {}).get("source_minutes") or 0), 2),
            "exports_used": int((totals or {}).get("exports_used") or 0),
            "stored_periods": int((totals or {}).get("periods") or 0),
            "scope": "all_stored_usage_periods",
        },
        "reservations": [
            {
                "kind": row.get("kind"),
                "status": row.get("status"),
                "count": int(row.get("count") or 0),
                "amount": round(float(row.get("amount") or 0), 2),
            }
            for row in reservations
        ],
    }


@router.get("/system-health", dependencies=[Depends(require_founder_admin_service)])
async def admin_system_health() -> dict[str, Any]:
    generated_at = _utc_now().isoformat()
    try:
        probe = await fetch_one("SELECT 1 AS ok")
        database_status = "healthy" if int((probe or {}).get("ok") or 0) == 1 else "degraded"
    except Exception:
        logger.exception("Founder admin database health read failed")
        database_status = "degraded"

    worker: dict[str, Any] = {"status": "unknown"}
    try:
        row = await fetch_one(
            """SELECT worker_id,status,started_at,heartbeat_at,last_error_code
               FROM worker_runtime_state WHERE id=1"""
        )
        if row:
            worker = {
                "status": row.get("status") or "unknown",
                "started_at": row.get("started_at"),
                "heartbeat_at": row.get("heartbeat_at"),
                "last_error_code": _text(row.get("last_error_code"), maximum=120),
            }
    except Exception:
        # A missing optional runtime-state table must not turn the health endpoint
        # into a write/migration path. Report unknown and remain read-only.
        worker = {"status": "unknown"}

    return {
        "generated_at": generated_at,
        "mode": "read_only",
        "database": {"status": database_status},
        "worker": worker,
        "external_provider_probes": "not_run",
    }


@router.get("/audit", dependencies=[Depends(require_founder_admin_service)])
async def admin_audit_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    total = await _count("SELECT COUNT(*) AS count FROM audit_events")
    rows = await fetch_all(
        """SELECT id,user_id,event,entity_type,entity_id,metadata_json,created_at
           FROM audit_events ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?""",
        (_bounded_limit(limit), _bounded_offset(offset)),
    )
    items = [
        {
            "id": row.get("id"),
            "user_id": row.get("user_id"),
            "event": row.get("event"),
            "entity_type": row.get("entity_type"),
            "entity_id": row.get("entity_id"),
            "metadata": _audit_metadata(row.get("metadata_json")),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]
    return {
        "items": items,
        "pagination": {"total": total, "limit": _bounded_limit(limit), "offset": _bounded_offset(offset)},
    }

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.database import execute, fetch_one


LEGAL_VERSION = "2026-08-09"
LEGAL_EFFECTIVE_DATE = "9 August 2026"
LEGAL_DOCUMENTS = (
    "terms",
    "privacy",
    "refund_policy",
    "acceptable_use",
    "copyright_policy",
)

_PLACEHOLDER_MARKERS = (
    "replace",
    "example.com",
    "your legal",
    "your business",
    "your address",
    "tbd",
    "todo",
    "placeholder",
    "__required",
    "changeme",
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{7,20}$")
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def legal_controls_required() -> bool:
    return get_settings().app_env.strip().lower() not in {"development", "test"}


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _looks_configured(value: str | None) -> bool:
    cleaned = _clean(value)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _email_configured(value: str | None) -> bool:
    cleaned = _clean(value)
    return _looks_configured(cleaned) and bool(_EMAIL_RE.fullmatch(cleaned))


def _phone_configured(value: str | None) -> bool:
    cleaned = _clean(value)
    if not _looks_configured(cleaned) or not _PHONE_RE.fullmatch(cleaned):
        return False
    digits = re.sub(r"\D", "", cleaned)
    return 10 <= len(digits) <= 15


def _name_configured(value: str | None) -> bool:
    cleaned = _clean(value)
    return _looks_configured(cleaned) and len(cleaned) >= 3


def _address_configured(value: str | None) -> bool:
    cleaned = _clean(value)
    return _looks_configured(cleaned) and len(cleaned) >= 15 and " " in cleaned


def legal_configuration_issues() -> list[str]:
    """Return public-launch blockers without exposing secret configuration."""
    settings = get_settings()
    checks = {
        "LEGAL_OPERATOR_NAME": _name_configured(settings.legal_operator_name),
        "LEGAL_OPERATOR_ADDRESS": _address_configured(settings.legal_operator_address),
        "LEGAL_CONTACT_EMAIL": _email_configured(settings.legal_contact_email),
        "PRIVACY_CONTACT_EMAIL": _email_configured(settings.privacy_contact_email),
        "CUSTOMER_CARE_EMAIL": _email_configured(settings.customer_care_email),
        "CUSTOMER_CARE_PHONE": _phone_configured(settings.customer_care_phone),
        "GRIEVANCE_OFFICER_NAME": _name_configured(settings.grievance_officer_name),
        "GRIEVANCE_EMAIL": _email_configured(settings.grievance_email),
        "GRIEVANCE_PHONE": _phone_configured(settings.grievance_phone),
    }
    issues = [key for key, ok in checks.items() if not ok]
    pan = _clean(settings.legal_pan).upper()
    gstin = _clean(settings.legal_gstin).upper()
    if pan and not _PAN_RE.fullmatch(pan):
        issues.append("LEGAL_PAN_INVALID")
    if gstin and not _GSTIN_RE.fullmatch(gstin):
        issues.append("LEGAL_GSTIN_INVALID")
    return issues


def paid_launch_ready() -> bool:
    return not legal_configuration_issues()


def checkout_allowed() -> tuple[bool, str]:
    """Determine if checkout should be allowed based on environment and Razorpay mode.

    Returns:
        tuple[bool, str]: (allowed, reason)
        - allowed: True if checkout can proceed
        - reason: explanation for the decision (for logging/debugging)
    """
    settings = get_settings()
    env = settings.app_env.strip().lower()
    is_development = env in {"development", "test"}
    mode = settings.normalized_razorpay_mode

    # Key/mode consistency check
    if not settings.razorpay_mode_key_consistent:
        return False, f"Razorpay mode '{mode}' does not match configured key type"

    # Live mode: staging/production always require complete public legal config.
    # Local development may explicitly opt in to live Razorpay for merchant-side
    # integration testing. The opt-in is deliberately server-side and cannot be
    # enabled by a browser/query parameter. Real money can be charged in this mode.
    if mode == "live":
        if is_development and settings.allow_live_razorpay_in_development:
            return True, "Live Razorpay explicitly enabled for local development"
        if paid_launch_ready():
            return True, "Live mode with complete legal config"
        return False, "Live mode requires complete production legal configuration"

    # Test mode
    if mode == "test":
        if is_development:
            return True, "Test mode in development environment"
        # Test mode in production-like env: still require legal config for safety
        if paid_launch_ready():
            return True, "Test mode with complete legal config"
        return False, "Test mode outside development requires complete legal config"

    return False, "Invalid Razorpay mode"


async def init_legal_compliance() -> None:
    """Install non-destructive legal state and the first-payment fail-closed gate.

    This is a startup migration, not a request-time helper. The checkout trigger
    is deliberately below FastAPI: a stale frontend or direct route cannot create
    a paid checkout without the current acceptance.
    """
    if get_settings().normalized_database_backend == "postgres":
        return
    await execute(
        """CREATE TABLE IF NOT EXISTS legal_acceptances (
             id TEXT PRIMARY KEY,
             user_id TEXT NOT NULL,
             version TEXT NOT NULL,
             documents_json TEXT NOT NULL,
             source TEXT NOT NULL,
             user_agent TEXT NOT NULL DEFAULT '',
             accepted_at TEXT NOT NULL,
             UNIQUE(user_id, version),
             FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
           )"""
    )
    await execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_acceptances_user ON legal_acceptances(user_id,accepted_at DESC)"
    )
    await execute(
        """CREATE TABLE IF NOT EXISTS privacy_requests (
             id TEXT PRIMARY KEY,
             user_id TEXT NOT NULL,
             kind TEXT NOT NULL CHECK(kind IN ('access','correction','deletion','grievance')),
             status TEXT NOT NULL CHECK(status IN ('received','in_review','completed','rejected')),
             details TEXT NOT NULL DEFAULT '',
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL,
             FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
           )"""
    )
    await execute(
        "CREATE INDEX IF NOT EXISTS idx_privacy_requests_user ON privacy_requests(user_id,created_at DESC)"
    )
    await execute(
        """CREATE TABLE IF NOT EXISTS legal_launch_state (
             id INTEGER PRIMARY KEY CHECK(id=1),
             enforcement_enabled INTEGER NOT NULL,
             paid_launch_ready INTEGER NOT NULL,
             version TEXT NOT NULL,
             updated_at TEXT NOT NULL
           )"""
    )
    await execute(
        """INSERT INTO legal_launch_state(id,enforcement_enabled,paid_launch_ready,version,updated_at)
           VALUES (1,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             enforcement_enabled=excluded.enforcement_enabled,
             paid_launch_ready=excluded.paid_launch_ready,
             version=excluded.version,
             updated_at=excluded.updated_at""",
        (1 if legal_controls_required() else 0, 1 if paid_launch_ready() else 0, LEGAL_VERSION, utcnow()),
    )
    await execute("DROP TRIGGER IF EXISTS trg_require_current_legal_before_paid_checkout")
    await execute(
        f"""CREATE TRIGGER trg_require_current_legal_before_paid_checkout
        BEFORE INSERT ON billing_checkouts
        WHEN COALESCE((SELECT enforcement_enabled FROM legal_launch_state WHERE id=1),0)=1
        BEGIN
          SELECT CASE WHEN COALESCE((SELECT paid_launch_ready FROM legal_launch_state WHERE id=1),0)=0
            THEN RAISE(ABORT,'LEGAL_CONFIGURATION_REQUIRED') END;
          SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM legal_acceptances
            WHERE user_id=NEW.user_id AND version='{LEGAL_VERSION}'
          ) THEN RAISE(ABORT,'LEGAL_ACCEPTANCE_REQUIRED') END;
        END"""
    )


def public_legal_config() -> dict:
    settings = get_settings()
    ready = paid_launch_ready()
    return {
        "service_name": settings.app_name,
        "website": settings.app_public_url,
        "version": LEGAL_VERSION,
        "effective_date": LEGAL_EFFECTIVE_DATE,
        "paid_launch_ready": ready,
        "operator_name": _clean(settings.legal_operator_name) if ready else "",
        "operator_address": _clean(settings.legal_operator_address) if ready else "",
        "legal_email": _clean(settings.legal_contact_email),
        "privacy_email": _clean(settings.privacy_contact_email),
        "customer_care_email": _clean(settings.customer_care_email),
        "customer_care_phone": _clean(settings.customer_care_phone),
        "grievance_officer_name": _clean(settings.grievance_officer_name),
        "grievance_email": _clean(settings.grievance_email),
        "grievance_phone": _clean(settings.grievance_phone),
        "gstin": _clean(settings.legal_gstin),
        "pan": _clean(settings.legal_pan),
        "documents": list(LEGAL_DOCUMENTS),
    }


async def record_legal_acceptance(user_id: str, version: str, *, source: str, user_agent: str = "") -> dict:
    if version != LEGAL_VERSION:
        raise ValueError("The legal document version is no longer current. Refresh and review the latest terms.")
    timestamp = utcnow()
    await execute(
        """INSERT INTO legal_acceptances(id,user_id,version,documents_json,source,user_agent,accepted_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(user_id,version) DO UPDATE SET
             documents_json=excluded.documents_json,source=excluded.source,
             user_agent=excluded.user_agent,accepted_at=excluded.accepted_at""",
        (str(uuid.uuid4()), user_id, LEGAL_VERSION, json.dumps(LEGAL_DOCUMENTS, separators=(",", ":")), source[:40], user_agent.strip()[:255], timestamp),
    )
    return {"accepted": True, "version": LEGAL_VERSION, "accepted_at": timestamp, "documents": list(LEGAL_DOCUMENTS)}


async def legal_status(user_id: str) -> dict:
    row = await fetch_one(
        "SELECT version,accepted_at FROM legal_acceptances WHERE user_id=? AND version=?",
        (user_id, LEGAL_VERSION),
    )
    allowed, reason = checkout_allowed()
    return {
        "version": LEGAL_VERSION,
        "effective_date": LEGAL_EFFECTIVE_DATE,
        "accepted": bool(row),
        "accepted_at": row.get("accepted_at") if row else None,
        "paid_launch_ready": paid_launch_ready(),
        "checkout_allowed": allowed,
        "checkout_reason": reason,
        "razorpay_mode": get_settings().normalized_razorpay_mode,
        "real_money": get_settings().normalized_razorpay_mode == "live",
        "development_live_opt_in": bool(
            get_settings().app_env.strip().lower() in {"development", "test"}
            and get_settings().allow_live_razorpay_in_development
        ),
    }


async def has_current_legal_acceptance(user_id: str) -> bool:
    status = await legal_status(user_id)
    return bool(status["accepted"])


async def create_privacy_request(user_id: str, kind: str, details: str = "") -> dict:
    if kind not in {"access", "correction", "deletion", "grievance"}:
        raise ValueError("Choose a valid privacy request type.")
    timestamp = utcnow()
    request_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO privacy_requests(id,user_id,kind,status,details,created_at,updated_at) VALUES (?,?,?,'received',?,?,?)",
        (request_id, user_id, kind, details.strip()[:1000], timestamp, timestamp),
    )
    return {"id": request_id, "kind": kind, "status": "received", "created_at": timestamp}

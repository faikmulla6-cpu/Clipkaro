from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.config import get_settings


_PLACEHOLDER_MARKERS = (
    "replace",
    "placeholder",
    "__required",
    "example.com",
    "your-verified-domain.com",
    "resend.dev",
    "changeme",
    "change-me",
    "dummy",
    "todo",
    "tbd",
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{7,20}$")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _placeholder(value: object) -> bool:
    text = _clean(value).lower()
    return not text or any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _email_ok(value: object) -> bool:
    text = _clean(value)
    return not _placeholder(text) and bool(_EMAIL_RE.fullmatch(text))


def _mailbox_ok(value: object) -> bool:
    """Validate either a bare mailbox or RFC-style ``Name <mailbox>`` sender."""
    text = _clean(value)
    if "<" in text and text.endswith(">"):
        text = text.rsplit("<", 1)[1][:-1].strip()
    return _email_ok(text)


def _phone_ok(value: object) -> bool:
    text = _clean(value)
    if _placeholder(text) or not _PHONE_RE.fullmatch(text):
        return False
    digits = re.sub(r"\D", "", text)
    return 10 <= len(digits) <= 15


def _https_url(value: object) -> bool:
    text = _clean(value)
    if _placeholder(text):
        return False
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname)


def _secret_ok(value: object, *, minimum: int = 32) -> bool:
    text = _clean(value)
    if _placeholder(text) or len(text) < minimum:
        return False
    # Reject extremely low-diversity values such as "aaaaaaaa....".
    return len(set(text)) >= 12


def production_boot_configuration_issues() -> list[str]:
    """Critical production boot requirements; contains codes only, never values."""
    settings = get_settings()
    issues: list[str] = []
    if not _secret_ok(settings.secret_key, minimum=32):
        issues.append("SECRET_KEY_WEAK")
    if not _https_url(settings.app_public_url):
        issues.append("APP_PUBLIC_URL_NOT_HTTPS")
    if not _https_url(settings.frontend_url):
        # Verification emails use FRONTEND_URL for one-time links. Production
        # must never emit password/email ownership links to plain HTTP or an
        # accidental localhost value.
        issues.append("FRONTEND_URL_NOT_HTTPS")
    origins = settings.allowed_origins
    if not origins or any(not _https_url(origin) for origin in origins):
        issues.append("CORS_ORIGINS_NOT_HTTPS")
    if settings.seed_demo_user:
        issues.append("SEED_DEMO_USER_ENABLED")
    if settings.allow_live_razorpay_in_development:
        issues.append("LIVE_RAZORPAY_DEVELOPMENT_OPT_IN_ENABLED")
    if settings.normalized_database_backend != "postgres":
        issues.append("PRODUCTION_DATABASE_NOT_POSTGRES")
    database_url = _clean(settings.database_url)
    if not database_url.startswith(("postgresql://", "postgres://")) or _placeholder(database_url):
        issues.append("DATABASE_URL_INVALID_OR_MISSING")
    if settings.normalized_storage_backend != "gcs":
        issues.append("PRODUCTION_STORAGE_NOT_GCS")
    if _placeholder(settings.gcs_bucket) or "://" in _clean(settings.gcs_bucket):
        issues.append("GCS_BUCKET_INVALID_OR_MISSING")
    if settings.normalized_job_backend != "cloud_run_job":
        issues.append("PRODUCTION_JOB_BACKEND_NOT_CLOUD_RUN")
    if any(_placeholder(value) for value in (
        settings.gcp_project_id, settings.gcp_region, settings.cloud_run_media_job_name,
    )):
        issues.append("CLOUD_RUN_JOB_CONFIGURATION_MISSING")
    if _clean(settings.frontend_url).rstrip("/") != "https://clipkaro.pro":
        issues.append("FRONTEND_URL_NOT_CLIPKARO_PRO")
    if set(settings.allowed_origins) != {"https://clipkaro.pro"}:
        issues.append("CORS_ORIGINS_NOT_LOCKED")
    if not _mailbox_ok(settings.email_from) or "resend.dev" in _clean(settings.email_from).lower():
        issues.append("EMAIL_FROM_NOT_EXPLICIT")
    if settings.normalized_razorpay_mode != "live":
        issues.append("RAZORPAY_MODE_NOT_LIVE")
    return issues


def paid_launch_configuration_issues() -> list[str]:
    """Offline shape/secret-policy blockers for paid launch.

    Provider reachability/authentication and legal particulars are checked by
    their dedicated production-preflight components. This function deliberately
    exposes only blocker codes.
    """
    settings = get_settings()
    issues = production_boot_configuration_issues()

    if not settings.production_credentials_rotated:
        issues.append("PRODUCTION_CREDENTIAL_ROTATION_UNCONFIRMED")

    resend_ready = (
        _secret_ok(settings.resend_api_key, minimum=20)
        and _mailbox_ok(settings.email_from)
    )
    smtp_ready = (
        bool(_clean(settings.smtp_host))
        and not _placeholder(settings.smtp_host)
        and _mailbox_ok(settings.smtp_from_email or settings.email_from)
        and bool(_clean(settings.smtp_username)) == bool(_clean(settings.smtp_password))
    )
    if not (resend_ready or smtp_ready):
        issues.append("TRANSACTIONAL_EMAIL_NOT_CONFIGURED")

    key_id = _clean(settings.razorpay_key_id)
    if not key_id.startswith("rzp_live_") or _placeholder(key_id):
        issues.append("RAZORPAY_LIVE_KEY_ID_MISSING")
    if not _secret_ok(settings.razorpay_key_secret, minimum=20):
        issues.append("RAZORPAY_KEY_SECRET_MISSING")
    if not _secret_ok(settings.razorpay_webhook_secret, minimum=32):
        issues.append("RAZORPAY_WEBHOOK_SECRET_WEAK")

    # Media-provider credentials intentionally live only in the isolated worker
    # in production. Their readiness is verified through the worker heartbeat
    # in production_preflight(), not by requiring secrets in the API process.

    return list(dict.fromkeys(issues))


def production_configuration_summary() -> dict[str, object]:
    """Secret-safe configuration summary suitable for logs/preflight."""
    settings = get_settings()
    blockers = paid_launch_configuration_issues()
    return {
        "ready": not blockers,
        "blocker_codes": blockers,
        "https_public_url": _https_url(settings.app_public_url),
        "https_frontend_url": _https_url(settings.frontend_url),
        "https_cors": bool(settings.allowed_origins) and all(_https_url(origin) for origin in settings.allowed_origins),
        "transactional_email_configured": (
            (_secret_ok(settings.resend_api_key, minimum=20) and _mailbox_ok(settings.email_from))
            or (bool(_clean(settings.smtp_host)) and _mailbox_ok(settings.smtp_from_email or settings.email_from))
        ),
        "resend_configured": _secret_ok(settings.resend_api_key, minimum=20) and _mailbox_ok(settings.email_from),
        "smtp_configured": bool(_clean(settings.smtp_host)) and _mailbox_ok(settings.smtp_from_email or settings.email_from),
        "razorpay_live_configured": (
            _clean(settings.razorpay_key_id).startswith("rzp_live_")
            and _secret_ok(settings.razorpay_key_secret, minimum=20)
            and _secret_ok(settings.razorpay_webhook_secret, minimum=32)
        ),
        "provider_credentials_checked_by_worker_preflight": True,
        "credentials_rotation_confirmed": bool(settings.production_credentials_rotated),
        "database_backend": settings.normalized_database_backend,
        "storage_backend": settings.normalized_storage_backend,
        "job_backend": settings.normalized_job_backend,
        "serverless_mode": settings.production_serverless_mode,
    }

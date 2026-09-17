from __future__ import annotations

import os
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


def _env(name: str) -> str:
    return _clean(os.environ.get(name, ""))


def _placeholder(value: object) -> bool:
    text = _clean(value).lower()
    return not text or any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _email_ok(value: object) -> bool:
    text = _clean(value)
    return not _placeholder(text) and bool(_EMAIL_RE.fullmatch(text))


def _mailbox_ok(value: object) -> bool:
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
    return len(set(text)) >= 12


def _object_storage_provider() -> str:
    value = _env("OBJECT_STORAGE_PROVIDER").lower()
    return value or "gcs"


def _job_execution_provider() -> str:
    value = _env("JOB_EXECUTION_PROVIDER").lower()
    return value or "cloud_run"


def _s3_configuration_ok() -> bool:
    return (
        _https_url(_env("S3_ENDPOINT_URL"))
        and not _placeholder(_env("S3_REGION"))
        and not _placeholder(_env("S3_BUCKET_NAME"))
        and not _placeholder(_env("S3_ACCESS_KEY_ID"))
        and _secret_ok(_env("S3_SECRET_ACCESS_KEY"), minimum=20)
    )


def _modal_configuration_ok() -> bool:
    return (
        not _placeholder(_env("MODAL_APP_NAME"))
        and not _placeholder(_env("MODAL_MEDIA_FUNCTION"))
    )


def production_boot_configuration_issues() -> list[str]:
    """Critical production boot requirements; contains codes only, never values."""
    settings = get_settings()
    issues: list[str] = []
    if not _secret_ok(settings.secret_key, minimum=32):
        issues.append("SECRET_KEY_WEAK")
    if not _https_url(settings.app_public_url):
        issues.append("APP_PUBLIC_URL_NOT_HTTPS")
    if not _https_url(settings.frontend_url):
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

    # `STORAGE_BACKEND=gcs` remains the validated cloud-storage compatibility
    # selector. The concrete provider is selected independently so GCP and Modal
    # can coexist without weakening local fail-closed behavior.
    if settings.normalized_storage_backend != "gcs":
        issues.append("PRODUCTION_STORAGE_NOT_CLOUD")
    object_provider = _object_storage_provider()
    if object_provider == "s3":
        if not _s3_configuration_ok():
            issues.append("S3_STORAGE_CONFIGURATION_MISSING")
    elif object_provider == "gcs":
        if _placeholder(settings.gcs_bucket) or "://" in _clean(settings.gcs_bucket):
            issues.append("GCS_BUCKET_INVALID_OR_MISSING")
    else:
        issues.append("OBJECT_STORAGE_PROVIDER_INVALID")

    if settings.normalized_job_backend != "cloud_run_job":
        issues.append("PRODUCTION_JOB_BACKEND_NOT_SERVERLESS")
    job_provider = _job_execution_provider()
    if job_provider == "modal":
        if not _modal_configuration_ok():
            issues.append("MODAL_JOB_CONFIGURATION_MISSING")
    elif job_provider == "cloud_run":
        if any(_placeholder(value) for value in (
            settings.gcp_project_id, settings.gcp_region, settings.cloud_run_media_job_name,
        )):
            issues.append("CLOUD_RUN_JOB_CONFIGURATION_MISSING")
    else:
        issues.append("JOB_EXECUTION_PROVIDER_INVALID")

    if _clean(settings.frontend_url).rstrip("/") != "https://clipkaro.pro":
        issues.append("FRONTEND_URL_NOT_CLIPKARO_PRO")
    if set(settings.allowed_origins) != {"https://clipkaro.pro"}:
        issues.append("CORS_ORIGINS_NOT_LOCKED")
    if not _mailbox_ok(settings.email_from) or "resend.dev" in _clean(settings.email_from).lower():
        issues.append("EMAIL_FROM_NOT_EXPLICIT")
    if settings.normalized_razorpay_mode != "live":
        issues.append("RAZORPAY_MODE_NOT_LIVE")

    youtube_provider = settings.normalized_youtube_ingestion_provider
    if youtube_provider in {"auto", "socialkit"}:
        if _placeholder(settings.socialkit_access_key):
            issues.append("YOUTUBE_INGESTION_PROVIDER_KEY_MISSING")
        if _clean(settings.socialkit_api_base_url).rstrip("/") != "https://api.socialkit.dev":
            issues.append("YOUTUBE_INGESTION_PROVIDER_URL_INVALID")
    return issues


def paid_launch_configuration_issues() -> list[str]:
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

    return list(dict.fromkeys(issues))


def production_configuration_summary() -> dict[str, object]:
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
        "provider_credentials_checked_by_media_runtime": True,
        "credentials_rotation_confirmed": bool(settings.production_credentials_rotated),
        "database_backend": settings.normalized_database_backend,
        "storage_backend": settings.normalized_storage_backend,
        "object_storage_provider": _object_storage_provider(),
        "job_backend": settings.normalized_job_backend,
        "job_execution_provider": _job_execution_provider(),
        "youtube_ingestion_provider": settings.normalized_youtube_ingestion_provider,
        "youtube_ingestion_provider_configured": (
            settings.normalized_youtube_ingestion_provider == "native"
            or not _placeholder(settings.socialkit_access_key)
        ),
        "serverless_mode": settings.production_serverless_mode,
    }

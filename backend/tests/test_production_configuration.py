from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services import production_configuration


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_default_production_shape_fails_closed_without_real_values() -> None:
    settings = get_settings()
    names = (
        "app_env", "secret_key", "app_public_url", "cors_origins", "seed_demo_user",
        "production_credentials_rotated", "resend_api_key", "email_from", "smtp_host", "smtp_from_email", "smtp_username",
        "smtp_password", "razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret",
        "groq_ranking_enabled", "groq_api_keys", "groq_api_key_1",
        "database_backend", "database_url", "storage_backend", "gcs_bucket", "job_backend",
        "gcp_project_id", "gcp_region", "cloud_run_media_job_name", "frontend_url", "razorpay_mode",
    )
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.secret_key = "replace-with-at-least-32-random-characters"
        settings.app_public_url = "http://localhost:3000"
        settings.cors_origins = "http://localhost:3000"
        settings.seed_demo_user = False
        settings.production_credentials_rotated = False
        settings.resend_api_key = ""
        settings.email_from = ""
        settings.smtp_host = ""
        settings.smtp_from_email = ""
        settings.smtp_username = ""
        settings.smtp_password = ""
        settings.razorpay_key_id = ""
        settings.razorpay_key_secret = ""
        settings.razorpay_webhook_secret = ""
        settings.groq_ranking_enabled = True
        settings.groq_api_keys = ""
        settings.groq_api_key_1 = ""
        issues = production_configuration.paid_launch_configuration_issues()
    finally:
        for name, value in original.items():
            setattr(settings, name, value)

    assert "SECRET_KEY_WEAK" in issues
    assert "APP_PUBLIC_URL_NOT_HTTPS" in issues
    assert "PRODUCTION_CREDENTIAL_ROTATION_UNCONFIRMED" in issues
    assert "TRANSACTIONAL_EMAIL_NOT_CONFIGURED" in issues
    assert "RAZORPAY_LIVE_KEY_ID_MISSING" in issues
    assert "GROQ_KEYS_MISSING" not in issues


def test_realistic_private_configuration_passes_offline_shape_checks() -> None:
    settings = get_settings()
    names = (
        "app_env", "secret_key", "app_public_url", "cors_origins", "seed_demo_user",
        "production_credentials_rotated", "resend_api_key", "email_from", "smtp_host", "smtp_from_email", "smtp_username",
        "smtp_password", "razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret",
        "groq_ranking_enabled", "groq_api_keys", "groq_api_key_1",
        "database_backend", "database_url", "storage_backend", "gcs_bucket", "job_backend",
        "gcp_project_id", "gcp_region", "cloud_run_media_job_name", "frontend_url", "razorpay_mode",
    )
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.secret_key = "Q5uH4mN7J2fS8xR1cK6pV3yT9zW0bL5dE7gA2nM4qP8sU1iO"
        settings.app_public_url = "https://clipkaro.pro"
        settings.cors_origins = "https://clipkaro.pro"
        settings.seed_demo_user = False
        settings.production_credentials_rotated = True
        settings.resend_api_key = "re_test_private_launch_secret_1234567890"
        settings.email_from = "ClipKaro AI <verify@mail.clipkaro.pro>"
        settings.smtp_host = ""
        settings.smtp_from_email = ""
        settings.smtp_username = ""
        settings.smtp_password = ""
        settings.razorpay_key_id = "rzp_live_test_1234567890"
        settings.razorpay_key_secret = "private-razorpay-secret-123456"
        settings.razorpay_webhook_secret = "webhook-private-secret-1234567890-abcdefghijk"
        settings.groq_ranking_enabled = True
        settings.groq_api_keys = ""
        settings.groq_api_key_1 = "gsk_test_private_key_shape_only"
        settings.database_backend = "postgres"
        settings.database_url = "postgresql://clipkaro:private@db.example.net/clipkaro?sslmode=require"
        settings.storage_backend = "gcs"
        settings.gcs_bucket = "clipkaro-private-production"
        settings.job_backend = "cloud_run_job"
        settings.gcp_project_id = "clipkaro-production"
        settings.gcp_region = "asia-south1"
        settings.cloud_run_media_job_name = "clipkaro-media"
        settings.frontend_url = "https://clipkaro.pro"
        settings.razorpay_mode = "live"
        assert production_configuration.paid_launch_configuration_issues() == []
        summary = production_configuration.production_configuration_summary()
    finally:
        for name, value in original.items():
            setattr(settings, name, value)

    assert summary["ready"] is True
    serialized = repr(summary).lower()
    assert "private-razorpay" not in serialized
    assert "smtp-password" not in serialized
    assert "gsk_private" not in serialized


def test_source_contract_never_commits_private_env_and_has_secure_configurator() -> None:
    gitignore = _read(".gitignore")
    compose = _read("docker-compose.hostinger.yml")
    main = _read("backend/app/main.py")
    preflight = _read("backend/app/services/production_preflight.py")
    configurator = _read("scripts/configure-production-env.py")
    checker = _read("scripts/check-production-env.py")

    assert ".env.production" in gitignore
    assert "production-*.env" in gitignore
    assert "PRODUCTION_CREDENTIALS_ROTATED" in compose
    assert "production_boot_configuration_issues" in main
    assert 'components["configuration"]' in preflight
    assert "secrets.token_urlsafe(64)" in configurator
    assert "secrets.token_urlsafe(48)" in configurator
    assert "os.chmod(path, 0o600)" in configurator
    assert "Secret values were not printed" in configurator
    assert '"blockers": blockers' in checker

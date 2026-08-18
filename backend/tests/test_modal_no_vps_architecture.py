from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.services.job_launcher import ModalJobLauncher, job_execution_provider_name
from app.services.production_configuration import production_boot_configuration_issues
from app.services.storage import S3StorageProvider, object_storage_provider_name


def test_modal_provider_selectors_are_explicit(monkeypatch) -> None:
    settings = get_settings()
    original_storage = settings.storage_backend
    original_jobs = settings.job_backend
    try:
        settings.storage_backend = "gcs"
        settings.job_backend = "cloud_run_job"
        monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "s3")
        monkeypatch.setenv("JOB_EXECUTION_PROVIDER", "modal")
        assert object_storage_provider_name() == "s3"
        assert job_execution_provider_name() == "modal"
    finally:
        settings.storage_backend = original_storage
        settings.job_backend = original_jobs


def test_s3_presigned_upload_is_private_and_content_type_bound(monkeypatch) -> None:
    captured = {}

    class FakeS3:
        def generate_presigned_url(self, operation, **kwargs):
            captured["operation"] = operation
            captured.update(kwargs)
            return "https://signed.example.invalid/upload"

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeS3())
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.example.invalid")
    monkeypatch.setenv("S3_REGION", "region-1")
    monkeypatch.setenv("S3_BUCKET_NAME", "private-bucket")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "access-key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret-key-value-1234567890")

    provider = S3StorageProvider()
    url = asyncio.run(provider.signed_upload_url(
        "quarantine/u1/session/video.mp4",
        content_type="video/mp4",
        ttl_seconds=900,
    ))
    assert url.startswith("https://")
    assert captured["operation"] == "put_object"
    assert captured["Params"] == {
        "Bucket": "private-bucket",
        "Key": "quarantine/u1/session/video.mp4",
        "ContentType": "video/mp4",
    }
    assert captured["HttpMethod"] == "PUT"


def test_modal_launcher_spawns_only_the_durable_job_id(monkeypatch) -> None:
    captured = {}

    class FakeCall:
        object_id = "fc-test"

    class FakeSpawn:
        async def aio(self, *args):
            captured["args"] = args
            return FakeCall()

    class FakeFunction:
        spawn = FakeSpawn()

    import modal
    monkeypatch.setattr(modal.Function, "from_name", lambda *args, **kwargs: FakeFunction())
    monkeypatch.setenv("MODAL_APP_NAME", "clipkaro-production")
    monkeypatch.setenv("MODAL_MEDIA_FUNCTION", "run_media_job")
    call_id = asyncio.run(ModalJobLauncher().launch("job-123"))
    assert call_id == "fc-test"
    assert captured["args"] == ("job-123",)


def test_modal_s3_production_boot_does_not_require_gcp(monkeypatch) -> None:
    settings = get_settings()
    names = (
        "app_env", "secret_key", "database_backend", "database_url",
        "storage_backend", "job_backend", "frontend_url", "app_public_url",
        "cors_origins", "email_from", "razorpay_mode", "seed_demo_user",
        "allow_live_razorpay_in_development",
    )
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.secret_key = "A9!clipkaro-production-secret-with-high-diversity-2026"
        settings.database_backend = "postgres"
        settings.database_url = "postgresql://user:pass@db.example.invalid/app?sslmode=require"
        settings.storage_backend = "gcs"
        settings.job_backend = "cloud_run_job"
        settings.frontend_url = "https://clipkaro.pro"
        settings.app_public_url = "https://clipkaro.pro"
        settings.cors_origins = "https://clipkaro.pro"
        settings.email_from = "ClipKaro AI <verify@clipkaro.pro>"
        settings.razorpay_mode = "live"
        settings.seed_demo_user = False
        settings.allow_live_razorpay_in_development = False
        monkeypatch.setenv("OBJECT_STORAGE_PROVIDER", "s3")
        monkeypatch.setenv("JOB_EXECUTION_PROVIDER", "modal")
        monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.example.invalid")
        monkeypatch.setenv("S3_REGION", "region-1")
        monkeypatch.setenv("S3_BUCKET_NAME", "private-bucket")
        monkeypatch.setenv("S3_ACCESS_KEY_ID", "access-key")
        monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret-key-with-enough-diversity-123")
        monkeypatch.setenv("MODAL_APP_NAME", "clipkaro-production")
        monkeypatch.setenv("MODAL_MEDIA_FUNCTION", "run_media_job")
        issues = production_boot_configuration_issues()
        assert "GCS_BUCKET_INVALID_OR_MISSING" not in issues
        assert "CLOUD_RUN_JOB_CONFIGURATION_MISSING" not in issues
        assert "S3_STORAGE_CONFIGURATION_MISSING" not in issues
        assert "MODAL_JOB_CONFIGURATION_MISSING" not in issues
    finally:
        for name, value in original.items():
            setattr(settings, name, value)


def test_modal_app_keeps_api_and_media_as_separate_functions() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "modal_app.py").read_text(encoding="utf-8")
    assert "@modal.asgi_app()" in source
    assert "def api()" in source
    assert "def run_media_job(job_id: str)" in source
    assert "modal.current_function_call_id()" in source
    assert "ffmpeg" in source and "clamav" in source and "libass9" in source
    assert 'modal.Secret.from_name(SECRET_NAME)' in source

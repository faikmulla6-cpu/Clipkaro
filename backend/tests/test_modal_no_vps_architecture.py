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


def test_s3_presigned_upload_and_bucket_probe(monkeypatch) -> None:
    captured = {}

    class FakeS3:
        def head_bucket(self, **kwargs):
            captured["head_bucket"] = kwargs
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

        def head_object(self, **kwargs):
            captured["head_object"] = kwargs
            error = RuntimeError("not found")
            error.response = {
                "ResponseMetadata": {"HTTPStatusCode": 404},
                "Error": {"Code": "NoSuchKey"},
            }
            raise error

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
    assert asyncio.run(provider.probe()) is True
    url = asyncio.run(
        provider.signed_upload_url(
            "quarantine/u1/session/video.mp4",
            content_type="video/mp4",
            ttl_seconds=900,
        )
    )
    assert url.startswith("https://")
    assert captured["head_bucket"] == {"Bucket": "private-bucket"}
    assert captured["head_object"] == {
        "Bucket": "private-bucket",
        "Key": "system/clipkaro-storage-readiness-probe",
    }
    assert captured["operation"] == "put_object"
    assert captured["Params"] == {
        "Bucket": "private-bucket",
        "Key": "quarantine/u1/session/video.mp4",
        "ContentType": "video/mp4",
    }
    assert captured["HttpMethod"] == "PUT"


def test_s3_probe_rejects_bucket_key_without_object_read_permission(monkeypatch) -> None:
    class FakeS3:
        def head_bucket(self, **kwargs):
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

        def head_object(self, **kwargs):
            error = RuntimeError("forbidden")
            error.response = {
                "ResponseMetadata": {"HTTPStatusCode": 403},
                "Error": {"Code": "403"},
            }
            raise error

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeS3())
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.example.invalid")
    monkeypatch.setenv("S3_REGION", "region-1")
    monkeypatch.setenv("S3_BUCKET_NAME", "private-bucket")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "access-key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret-key-value-1234567890")

    assert asyncio.run(S3StorageProvider().probe()) is False


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

    monkeypatch.setattr(
        modal.Function,
        "from_name",
        lambda *args, **kwargs: FakeFunction(),
    )
    monkeypatch.setenv("MODAL_APP_NAME", "clipkaro-production")
    monkeypatch.setenv("MODAL_MEDIA_FUNCTION", "run_media_job")
    call_id = asyncio.run(ModalJobLauncher().launch("job-123"))
    assert call_id == "fc-test"
    assert captured["args"] == ("job-123",)


def test_modal_s3_production_boot_does_not_require_gcp(monkeypatch) -> None:
    settings = get_settings()
    names = (
        "app_env",
        "secret_key",
        "post_karo_encryption_key",
        "database_backend",
        "database_url",
        "storage_backend",
        "job_backend",
        "frontend_url",
        "app_public_url",
        "cors_origins",
        "email_from",
        "razorpay_mode",
        "seed_demo_user",
        "allow_live_razorpay_in_development",
    )
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.secret_key = "A9!clipkaro-production-secret-with-high-diversity-2026"
        settings.post_karo_encryption_key = "Pk8!clipkaro-post-karo-secret-with-high-diversity-2026"
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
    assert 'modal.Secret.from_name(POST_KARO_SECRET_NAME)' in source
    assert 'secrets=[production_secret, post_karo_secret]' in source


def test_export_mobile_safety_contract_is_single_flight_and_server_authoritative() -> None:
    root = Path(__file__).resolve().parents[1]
    worker = (root / "app/api/worker_jobs.py").read_text(encoding="utf-8")
    routes = (root / "app/api/routes.py").read_text(encoding="utf-8")
    media = (root / "app/media_job.py").read_text(encoding="utf-8")
    rendering = (root / "app/services/rendering.py").read_text(encoding="utf-8")
    editor = (root.parent / "frontend/app/editor/[clipId]/page.tsx").read_text(encoding="utf-8")
    exports_page = (root.parent / "frontend/app/exports/page.tsx").read_text(encoding="utf-8")

    # API-side serialization is the cross-container authority against rapid
    # double taps, retries and multiple open tabs reserving duplicate Shorts.
    assert "distributed_advisory_lock(lock_key)" in worker
    assert "_active_export_for_clip" in worker
    assert "This Short is already rendering" in worker

    # Entitlements are normalized before the durable job payload is persisted.
    assert 'effective_watermark = True if active_plan == "free" else bool(body.watermark)' in worker
    assert 'payload={"request": effective_body.model_dump(mode="json")}' in worker

    # If job creation or Modal launch fails, the export reaches failed rather
    # than being deleted while a quota reservation is still attached to it.
    assert 'UPDATE exports SET status=\'failed\',error=? WHERE id=?' in worker
    assert 'DELETE FROM exports WHERE id=?' not in worker

    # Both durable Modal and legacy/local rendering preserve explicit creator
    # placement. Existing subtitles can inform the UI, never silently move it.
    assert "request.caption_position," in media
    assert "Creator choice is authoritative" in media
    assert "effective_position=" not in routes
    assert "request.focus_x, caption_position" in routes
    assert "caption_position=effective_caption_position(" in routes

    # Centre is a true centre for every Studio personality, including India Pop,
    # rather than accidentally falling through to the lower safe-area rule.
    assert "def _caption_y_center" in rendering
    assert 'if caption_position == "center":' in rendering
    assert "return height // 2" in rendering
    assert rendering.count("_caption_y_center(height, style, caption_position)") >= 2

    # Database reservation triggers own usage settlement. Legacy render/process
    # paths must not double-increment the already reserved counters.
    assert "UPDATE usage SET exports_used=exports_used+1" not in routes
    assert "UPDATE usage SET source_minutes=source_minutes+?" not in routes

    # Mobile UI guards the first few milliseconds before React state disables
    # buttons, ignores stale job streams, and checks readiness before download.
    assert "renderStartRef.current" in editor
    assert "activeJobRef.current !== jobId" in editor
    assert "downloadReadyExport" in editor
    assert 'user.plan === "free"' in editor
    assert "downloadExport" in exports_page
    assert 'api<ExportStatus>(`/exports/${exportId}`)' in exports_page


def test_production_socialkit_mode_fails_closed_without_server_key(monkeypatch) -> None:
    settings = get_settings()
    names = (
        "app_env", "secret_key", "post_karo_encryption_key", "database_backend", "database_url", "storage_backend",
        "job_backend", "frontend_url", "app_public_url", "cors_origins", "email_from",
        "razorpay_mode", "seed_demo_user", "allow_live_razorpay_in_development",
        "youtube_ingestion_provider", "socialkit_access_key", "socialkit_api_base_url",
    )
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.secret_key = "A9!clipkaro-production-secret-with-high-diversity-2026"
        settings.post_karo_encryption_key = "Pk8!clipkaro-post-karo-secret-with-high-diversity-2026"
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
        settings.youtube_ingestion_provider = "socialkit"
        settings.socialkit_access_key = ""
        settings.socialkit_api_base_url = "https://api.socialkit.dev"
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
        assert "YOUTUBE_INGESTION_PROVIDER_KEY_MISSING" in issues
        settings.socialkit_access_key = "sk_live_provider_key_with_enough_length_123"
        issues = production_boot_configuration_issues()
        assert "YOUTUBE_INGESTION_PROVIDER_KEY_MISSING" not in issues
    finally:
        for name, value in original.items():
            setattr(settings, name, value)


def test_production_worker_mode_requires_https_url_and_strong_secret(monkeypatch) -> None:
    settings = get_settings()
    names = (
        "app_env", "secret_key", "post_karo_encryption_key", "database_backend", "database_url", "storage_backend",
        "job_backend", "frontend_url", "app_public_url", "cors_origins", "email_from",
        "razorpay_mode", "seed_demo_user", "allow_live_razorpay_in_development",
        "youtube_ingestion_provider", "youtube_ingestion_worker_url", "youtube_ingestion_worker_secret",
    )
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.secret_key = "A9!clipkaro-production-secret-with-high-diversity-2026"
        settings.post_karo_encryption_key = "Pk8!clipkaro-post-karo-secret-with-high-diversity-2026"
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
        settings.youtube_ingestion_provider = "worker"
        settings.youtube_ingestion_worker_url = "http://worker.example.com"
        settings.youtube_ingestion_worker_secret = "short"
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
        assert "YOUTUBE_INGESTION_WORKER_URL_INVALID" in issues
        assert "YOUTUBE_INGESTION_WORKER_SECRET_WEAK" in issues

        settings.youtube_ingestion_worker_url = "https://ingest.clipkaro.pro"
        settings.youtube_ingestion_worker_secret = "A9-worker-secret-with-enough-diversity-2026!"
        issues = production_boot_configuration_issues()
        assert "YOUTUBE_INGESTION_WORKER_URL_INVALID" not in issues
        assert "YOUTUBE_INGESTION_WORKER_SECRET_WEAK" not in issues
    finally:
        for name, value in original.items():
            setattr(settings, name, value)


def test_media_wrapper_preserves_project_level_failure_truth() -> None:
    root = Path(__file__).resolve().parents[1]
    media = (root / "app/media_job.py").read_text(encoding="utf-8")
    direct_upload = (root.parent / "frontend/components/DirectUploadFallback.tsx").read_text(encoding="utf-8")
    assert 'current_job = await fetch_one("SELECT status FROM jobs WHERE id=?", (job["id"],))' in media
    assert 'if current_job and current_job.get("status") == "failed":' in media
    assert 'const diagnostic = job.message || job.error' in direct_upload

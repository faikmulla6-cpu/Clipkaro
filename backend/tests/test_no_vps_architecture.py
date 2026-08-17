from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.database import _postgres_query
from app.services.job_launcher import CloudRunJobLauncher, LocalJobLauncher
from app.services.storage import LocalStorageProvider, validate_object_key


def test_backend_selection_defaults_keep_local_development() -> None:
    settings = get_settings()
    assert settings.normalized_database_backend == "sqlite"
    assert settings.normalized_storage_backend == "local"
    assert settings.normalized_job_backend == "local"


def test_production_serverless_mode_requires_all_three_backends() -> None:
    settings = get_settings()
    names = ("app_env", "database_backend", "storage_backend", "job_backend")
    original = {name: getattr(settings, name) for name in names}
    try:
        settings.app_env = "production"
        settings.database_backend = "postgres"
        settings.storage_backend = "gcs"
        settings.job_backend = "cloud_run_job"
        assert settings.production_serverless_mode is True
        settings.storage_backend = "local"
        assert settings.production_serverless_mode is False
    finally:
        for name, value in original.items():
            setattr(settings, name, value)


@pytest.mark.parametrize("key", ["../secret", "/absolute", "users/a/../../b", "", "gs://bucket/key"])
def test_storage_rejects_untrusted_keys(key: str) -> None:
    with pytest.raises(ValueError):
        validate_object_key(key)


def test_storage_enforces_owner_prefix() -> None:
    assert validate_object_key("users/u1/exports/e1/clip.mp4", expected_prefix="users/u1/exports/e1")
    with pytest.raises(ValueError):
        validate_object_key("users/u2/exports/e1/clip.mp4", expected_prefix="users/u1")


def test_local_storage_round_trip_and_exact_delete(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path)
    source = tmp_path / "input.bin"
    source.write_bytes(b"private-media")
    metadata = asyncio.run(provider.upload(source, "users/u1/projects/p1/source/video.bin", content_type="application/octet-stream"))
    assert metadata.size == 13
    destination = tmp_path / "download.bin"
    asyncio.run(provider.download(metadata.key, destination))
    assert destination.read_bytes() == b"private-media"
    assert asyncio.run(provider.delete(metadata.key)) is True
    assert asyncio.run(provider.stat(metadata.key)) is None


def test_postgres_placeholder_translation_and_conflict_semantics() -> None:
    assert _postgres_query("SELECT * FROM users WHERE id=? AND email=?") == "SELECT * FROM users WHERE id=$1 AND email=$2"
    translated = _postgres_query("INSERT OR IGNORE INTO clip_behavior_events(id,event_key) VALUES (?,?)")
    assert translated.startswith("INSERT INTO clip_behavior_events")
    assert translated.endswith("ON CONFLICT DO NOTHING")


def test_local_job_launcher_never_contacts_cloud() -> None:
    assert asyncio.run(LocalJobLauncher().launch("job-id")) is None


def test_cloud_run_launcher_overrides_only_job_id(monkeypatch) -> None:
    from google.cloud import run_v2
    settings = get_settings()
    names = ("gcp_project_id", "gcp_region", "cloud_run_media_job_name", "cloud_run_job_timeout_seconds")
    original = {name: getattr(settings, name) for name in names}
    captured = {}

    class FakeClient:
        def run_job(self, *, request):
            captured.update(request)
            return object()

    try:
        settings.gcp_project_id = "project"
        settings.gcp_region = "asia-south1"
        settings.cloud_run_media_job_name = "media"
        settings.cloud_run_job_timeout_seconds = 2
        monkeypatch.setattr(run_v2, "JobsClient", FakeClient)
        asyncio.run(CloudRunJobLauncher().launch("job-123"))
    finally:
        for name, value in original.items():
            setattr(settings, name, value)

    overrides = captured["overrides"]
    assert overrides["task_count"] == 1
    assert overrides["container_overrides"] == [{"env": [{"name": "JOB_ID", "value": "job-123"}]}]


def test_serverless_source_contracts_are_present() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (root / "backend/migrations/versions/20260817_01_no_vps_schema.py").read_text(encoding="utf-8")
    dockerfile = (root / "backend/Dockerfile").read_text(encoding="utf-8")
    frontend = (root / "frontend/components/UploadStudio.tsx").read_text(encoding="utf-8")
    assert "uq_active_checkout_per_user" in migration
    assert "FOR UPDATE" in migration
    assert "upload_sessions" in migration
    assert "session_version INTEGER NOT NULL DEFAULT 0" in migration
    assert "send_window_started_at TEXT NOT NULL" in migration
    assert "suggestion_rank INTEGER NOT NULL" in migration
    assert "documents_json TEXT NOT NULL" in migration
    assert "FROM worker AS media" in dockerfile
    assert 'NEXT_PUBLIC_UPLOAD_MODE === "direct_gcs"' in frontend
    assert "/uploads/init" in frontend and "/complete" in frontend

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import routes as project_routes
from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.main import _auth_requests, _requests, app
from app.services.jobs import claim_next_job, create_job
from app.worker import run_claimed_job


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
        "app_env": settings.app_env,
        "email_verification_required": settings.email_verification_required,
        "upload_scan_required": settings.upload_scan_required,
        "clamav_host": settings.clamav_host,
        "job_execution_mode": settings.job_execution_mode,
    }
    settings.database_path = tmp_path / "reprocess-integrity.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "reprocess-integrity-secret-with-32-chars"
    settings.seed_demo_user = False
    settings.app_env = "test"
    settings.email_verification_required = False
    settings.upload_scan_required = False
    settings.clamav_host = ""
    settings.job_execution_mode = "worker"
    _requests.clear()
    _auth_requests.clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
        _requests.clear()
        _auth_requests.clear()


def _signup(client: TestClient, email: str = "reprocess@example.com") -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={"name": "Reprocess Creator", "email": email, "password": "Secure123"},
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email=?", (email,)))
    assert user
    return user


def _seed_ready_project(user_id: str, *, suffix: str = "a") -> tuple[str, str]:
    timestamp = "2026-08-16T00:00:00+00:00"
    project_id = f"project-{suffix}"
    video_id = f"video-{suffix}"
    asyncio.run(execute(
        "INSERT INTO projects VALUES (?, ?, ?, '', 'ready', 100, 'ready', 'auto', 'auto', NULL, ?, ?)",
        (project_id, user_id, "Existing project", timestamp, timestamp),
    ))
    source_path = get_settings().upload_dir / f"{video_id}.mp4"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"retained-test-source")
    asyncio.run(execute(
        "INSERT INTO videos(id,project_id,original_filename,duration,width,height,file_size,file_path,status,created_at,expires_at) VALUES (?, ?, ?, 90, 720, 1280, 100, ?, 'ready', ?, ?)",
        (video_id, project_id, "source.mp4", str(source_path), timestamp, timestamp),
    ))
    return project_id, video_id


def test_explicit_reprocess_persists_force_transcribe_and_durable_route(client: TestClient):
    user = _signup(client)
    project_id, video_id = _seed_ready_project(user["id"], suffix="force")

    response = client.post(f"/api/v1/projects/{project_id}/reprocess", json={"language": "hinglish"})
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    payload_row = asyncio.run(fetch_one("SELECT payload_json FROM job_payloads WHERE job_id=?", (job_id,)))
    assert payload_row
    payload = json.loads(payload_row["payload_json"])
    assert payload["video_id"] == video_id
    assert payload["force_transcribe"] is True
    assert payload["asr_route"] in {"legacy", "elevenlabs_roman"}
    assert payload["hinglish_rollout_stage"] in {"legacy", "stage1"}


def test_reprocess_is_rejected_while_project_or_export_is_active(client: TestClient):
    user = _signup(client, "reprocess-busy@example.com")
    project_id, video_id = _seed_ready_project(user["id"], suffix="busy")
    timestamp = "2026-08-16T00:00:00+00:00"
    clip_id = "clip-busy"
    asyncio.run(execute(
        "INSERT INTO clips VALUES (?, ?, 0, 30, 'Hook', 'Title', 'Reason', 'Text', 80, '{}', 'shorts', 'suggested', ?, ?)",
        (clip_id, video_id, timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO exports(id,clip_id,user_id,output_path,resolution,aspect_ratio,caption_style,watermark,status,progress,error,created_at,expires_at) VALUES (?, ?, ?, ?, '720p', '9:16', 'clean', 1, 'queued', 0, NULL, ?, ?)",
        ("export-busy", clip_id, user["id"], str(get_settings().export_dir / "busy.mp4"), timestamp, timestamp),
    ))

    blocked = client.post(f"/api/v1/projects/{project_id}/reprocess", json={"language": "hi"})
    assert blocked.status_code == 409
    assert "export" in blocked.json()["detail"].lower()

    asyncio.run(execute("UPDATE exports SET status='ready' WHERE id='export-busy'"))
    asyncio.run(execute("UPDATE projects SET status='processing' WHERE id=?", (project_id,)))
    blocked = client.post(f"/api/v1/projects/{project_id}/reprocess", json={"language": "hi"})
    assert blocked.status_code == 409
    assert "already being processed" in blocked.json()["detail"].lower()


def test_reanalysis_preserves_historical_exports_and_hides_superseded_moments(client: TestClient):
    user = _signup(client, "history@example.com")
    project_id, video_id = _seed_ready_project(user["id"], suffix="history")
    timestamp = "2026-08-16T00:00:00+00:00"
    exported_clip = "clip-exported-old"
    disposable_clip = "clip-disposable-old"
    asyncio.run(execute(
        "INSERT INTO clips VALUES (?, ?, 0, 30, 'Old export', 'Old exported', 'Reason', 'Text', 70, '{}', 'shorts', 'exported', ?, ?)",
        (exported_clip, video_id, timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO clips VALUES (?, ?, 30, 60, 'Old suggestion', 'Old unexported', 'Reason', 'Text', 65, '{}', 'shorts', 'suggested', ?, ?)",
        (disposable_clip, video_id, timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO exports(id,clip_id,user_id,output_path,resolution,aspect_ratio,caption_style,watermark,status,progress,error,created_at,expires_at) VALUES (?, ?, ?, ?, '720p', '9:16', 'clean', 1, 'ready', 100, NULL, ?, ?)",
        ("export-history", exported_clip, user["id"], str(get_settings().export_dir / "history.mp4"), timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO scheduled_posts VALUES (?, ?, ?, 'youtube', 'Caption', '#clipkaro', ?, 'draft', ?)",
        ("schedule-history", user["id"], "export-history", "2026-08-20T00:00:00+00:00", timestamp),
    ))

    new_clips = [{
        "id": "clip-new", "start_time": 5.0, "end_time": 35.0, "hook": "New hook",
        "title": "New title", "reason": "New analysis", "text": "New transcript",
        "score": 91.0, "score_breakdown": {"hook": 90}, "platform": "shorts",
    }]
    segments = [{"start": 0.0, "end": 40.0, "text": "New transcript words"}]
    with patch("app.api.routes.find_best_clips", new=AsyncMock(return_value=new_clips)):
        result = asyncio.run(project_routes._persist_suggestions({"id": video_id}, segments, "en"))
    assert result[0]["id"] == "clip-new"

    old_exported = asyncio.run(fetch_one("SELECT status FROM clips WHERE id=?", (exported_clip,)))
    assert old_exported and old_exported["status"] == "superseded"
    assert asyncio.run(fetch_one("SELECT id FROM clips WHERE id=?", (disposable_clip,))) is None
    assert asyncio.run(fetch_one("SELECT id FROM exports WHERE id='export-history'")) is not None
    assert asyncio.run(fetch_one("SELECT id FROM scheduled_posts WHERE id='schedule-history'")) is not None
    active = asyncio.run(fetch_all("SELECT id FROM clips WHERE video_id=? AND status<>'superseded'", (video_id,)))
    assert [row["id"] for row in active] == ["clip-new"]

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    row = next(item for item in projects.json() if item["id"] == project_id)
    assert row["clip_count"] == 1
    assert row["export_count"] == 1

    analytics = client.get("/api/v1/analytics")
    assert analytics.status_code == 200
    summary = analytics.json()["summary"]
    assert summary["clips"] == 1
    assert summary["exports"] == 1
    assert summary["minutes_processed"] == 1.5


def test_worker_replays_force_transcribe_flag_for_same_durable_job(client: TestClient):
    user = _signup(client, "force-worker@example.com")
    project_id, video_id = _seed_ready_project(user["id"], suffix="worker")
    payload = {
        "video_id": video_id,
        "force_transcribe": True,
        "asr_route": "legacy",
        "hinglish_rollout_stage": "legacy",
    }
    job_id = asyncio.run(create_job(user["id"], "process_video", project_id=project_id, payload=payload))
    claimed = asyncio.run(claim_next_job("force-worker"))
    assert claimed and claimed["id"] == job_id

    process = AsyncMock()
    with patch("app.api.routes._process_project", new=process):
        asyncio.run(run_claimed_job(claimed))
    process.assert_awaited_once()
    assert process.await_args.args[0] == job_id
    assert process.await_args.args[4] == "legacy"
    assert process.await_args.args[5] is True

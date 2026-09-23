import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_one
from app.main import _auth_requests, _requests, app
from app.schemas.api import ExportRequest
from app.services.jobs import claim_next_job, create_job, release_claim, requeue_interrupted_worker_jobs
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
    settings.database_path = tmp_path / "worker-isolation.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "worker-isolation-test-secret-with-32-characters"
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


def _signup(client: TestClient, email: str = "worker@example.com") -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={"name": "Worker Creator", "email": email, "password": "Secure123"},
    )
    assert response.status_code == 201, response.text
    user = asyncio.run(fetch_one("SELECT * FROM users WHERE email=?", (email,)))
    assert user
    return user


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def test_worker_mode_upload_only_enqueues_and_persists_video_payload(client: TestClient):
    user = _signup(client)
    with patch("app.api.routes._process_project", new=AsyncMock()) as process:
        response = client.post(
            "/api/v1/projects/upload",
            headers=_csrf(client),
            files={"file": ("queued.mp4", b"fixture-video", "video/mp4")},
            data={"title": "Queued securely"},
        )
    assert response.status_code == 201, response.text
    process.assert_not_awaited()
    job_id = response.json()["job_id"]
    job = asyncio.run(fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,)))
    payload = asyncio.run(fetch_one("SELECT * FROM job_payloads WHERE job_id=?", (job_id,)))
    assert job and job["status"] == "queued"
    assert job["user_id"] == user["id"]
    assert payload and response.json()["video_id"] in payload["payload_json"]
    assert '"asr_route":"legacy"' in payload["payload_json"]
    assert '"hinglish_rollout_stage":"legacy"' in payload["payload_json"]


def test_atomic_worker_claim_exposes_durable_payload_once(client: TestClient):
    user = _signup(client, "claim@example.com")
    job_id = asyncio.run(create_job(user["id"], "process_video", project_id="project-x", payload={"video_id": "video-x"}))
    first = asyncio.run(claim_next_job("worker-a"))
    second = asyncio.run(claim_next_job("worker-b"))
    assert first and first["id"] == job_id
    assert first["payload"] == {"video_id": "video-x"}
    assert second is None
    claim = asyncio.run(fetch_one("SELECT * FROM job_claims WHERE job_id=?", (job_id,)))
    assert claim and claim["worker_id"] == "worker-a"
    asyncio.run(release_claim(job_id))


def test_worker_restart_and_requeue_preserve_persisted_route(client: TestClient):
    user = _signup(client, "route-restart@example.com")
    payload = {"video_id": "video-x", "asr_route": "elevenlabs_roman", "hinglish_rollout_stage": "stage1"}
    job_id = asyncio.run(create_job(user["id"], "process_video", project_id="project-x", payload=payload))
    claimed = asyncio.run(claim_next_job("old-worker"))
    assert claimed and claimed["payload"] == payload
    assert asyncio.run(requeue_interrupted_worker_jobs()) == 1
    resumed = asyncio.run(claim_next_job("fresh-worker"))
    assert resumed and resumed["id"] == job_id
    assert resumed["payload"] == payload
    asyncio.run(release_claim(job_id))


def test_worker_reconstructs_full_export_request_before_render(client: TestClient):
    user = _signup(client, "render-worker@example.com")
    timestamp = "2026-08-08T00:00:00+00:00"
    project_id, video_id, clip_id, export_id = "project-r", "video-r", "clip-r", "export-r"
    video_path = get_settings().upload_dir / "video-r.mp4"
    output_path = get_settings().export_dir / "export-r.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fixture")
    asyncio.run(execute(
        "INSERT INTO projects VALUES (?, ?, ?, '', 'ready', 100, 'ready', 'auto', 'auto', NULL, ?, ?)",
        (project_id, user["id"], "Render project", timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO videos VALUES (?, ?, ?, 60, 1080, 1920, 7, ?, 'ready', ?, ?)",
        (video_id, project_id, "video.mp4", str(video_path), timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO clips VALUES (?, ?, 1, 31, ?, ?, ?, ?, 88, '{}', 'shorts', 'suggested', ?, ?)",
        (clip_id, video_id, "Original hook", "Title", "Reason", "Transcript", timestamp, timestamp),
    ))
    asyncio.run(execute(
        "INSERT INTO exports VALUES (?, ?, ?, ?, '1080p', '9:16', 'bold', 0, 'queued', 0, NULL, ?, ?)",
        (export_id, clip_id, user["id"], str(output_path), timestamp, timestamp),
    ))
    request = ExportRequest(
        resolution="1080p",
        caption_style="bold",
        hook_text="Custom durable hook",
        hook_enabled=False,
        watermark=False,
        focus_x=37,
        caption_position="above",
    )
    job_id = asyncio.run(create_job(
        user["id"], "render_export", export_id=export_id,
        payload={"request": request.model_dump(mode="json")},
    ))
    claimed = asyncio.run(claim_next_job("render-worker"))
    assert claimed and claimed["id"] == job_id

    render = AsyncMock()
    with patch("app.api.routes._render_export", new=render):
        asyncio.run(run_claimed_job(claimed))
    render.assert_awaited_once()
    restored = render.await_args.args[4]
    assert restored.hook_text == "Custom durable hook"
    assert restored.hook_enabled is False
    assert restored.resolved_hook_text("Original hook") == ""
    assert restored.resolution == "1080p"
    assert restored.caption_style == "bold"
    assert restored.focus_x == 37
    assert restored.caption_position == "above"
    assert restored.watermark is False
    assert asyncio.run(fetch_one("SELECT * FROM job_claims WHERE job_id=?", (job_id,))) is None

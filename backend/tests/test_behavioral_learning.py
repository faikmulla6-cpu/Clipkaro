from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.main import _auth_requests, _requests, app
from app.services.behavioral_learning import learning_rows


@pytest.fixture()
def client(tmp_path):
    # Rate-limit buckets are process-global by design. Reset only the in-memory
    # test buckets so this module is order-independent inside the full suite.
    _requests.clear()
    _auth_requests.clear()
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
        "upload_scan_required": settings.upload_scan_required,
    }
    settings.app_env = "test"
    settings.database_path = tmp_path / "behavior.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = True
    settings.upload_scan_required = False
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        _requests.clear()
        _auth_requests.clear()
        for key, value in original.items():
            setattr(settings, key, value)


def login_demo(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@clipkaro.ai", "password": "ClipKaro123!"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")


def create_suggestions(client: TestClient, title: str = "Learning source") -> tuple[str, list[dict]]:
    with patch("app.api.routes._process_project", new=AsyncMock()):
        upload = client.post(
            "/api/v1/projects/upload",
            data={"title": title},
            files={"file": ("learning.mp4", b"test-video", "video/mp4")},
        )
    assert upload.status_code == 201
    project_id = upload.json()["id"]
    segments = [
        {"start": 0, "end": 16, "text": "Why do most creators lose attention before the useful part begins?"},
        {"start": 16, "end": 32, "text": "The first fix is to promise one clear result and remove the long introduction."},
        {"start": 32, "end": 50, "text": "Here is the second step: show a specific example so the viewer can trust the advice."},
        {"start": 50, "end": 68, "text": "The surprising part is that shorter explanations often create more clarity, not less."},
        {"start": 68, "end": 86, "text": "Avoid this common mistake: do not repeat the same setup after the value is already clear."},
        {"start": 86, "end": 106, "text": "Use these three steps and the audience gets a complete thought with a satisfying ending."},
    ]
    analysis = client.post(
        f"/api/v1/projects/{project_id}/analyse",
        json={"language": "en", "segments": segments},
    )
    assert analysis.status_code == 200
    clips = analysis.json()
    assert clips
    return project_id, clips


def attach_ranking_provenance(project_id: str, source: str = "local") -> None:
    asyncio.run(execute(
        "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
        (
            f"rank-audit-{project_id}-{source}", "demo-user", "project.processed", "project", project_id,
            json.dumps({"ranking_source": source}), "2026-08-09T10:00:00+00:00",
        ),
    ))


def test_suggestion_generation_is_ranked_and_privacy_minimized(client: TestClient) -> None:
    login_demo(client)
    project_id, clips = create_suggestions(client)
    generations = asyncio.run(fetch_all(
        "SELECT * FROM recommendation_generations WHERE project_id=? ORDER BY created_at",
        (project_id,),
    ))
    assert len(generations) == 1
    assert generations[0]["ranking_source"] == "pending"
    snapshots = asyncio.run(fetch_all(
        "SELECT * FROM clip_suggestion_snapshots WHERE generation_id=? ORDER BY suggestion_rank",
        (generations[0]["id"],),
    ))
    assert len(snapshots) == len(clips)
    assert [row["suggestion_rank"] for row in snapshots] == list(range(1, len(snapshots) + 1))
    assert [row["clip_id"] for row in snapshots] == [clip["id"] for clip in clips]
    assert all("transcript" not in key for key in snapshots[0].keys())

    attach_ranking_provenance(project_id, "groq")
    updated = asyncio.run(fetch_one(
        "SELECT ranking_source,ranking_model FROM recommendation_generations WHERE id=?",
        (generations[0]["id"],),
    ))
    assert updated == {"ranking_source": "groq", "ranking_model": "groq-configured"}
    snapshot = asyncio.run(fetch_one(
        "SELECT ranking_source,ranking_model FROM clip_suggestion_snapshots WHERE generation_id=? LIMIT 1",
        (generations[0]["id"],),
    ))
    assert snapshot == updated


def test_client_events_are_hashed_idempotent_strict_and_owned(client: TestClient) -> None:
    login_demo(client)
    _, clips = create_suggestions(client)
    clip_id = clips[0]["id"]
    payload = {
        "event_type": "impression",
        "client_event_id": "creator@example.com:page-session-1:impression:first",
        "client_session_id": "creator@example.com:page-session-1",
        "surface": "project",
    }
    first = client.post(f"/api/v1/clips/{clip_id}/behavior", json=payload)
    second = client.post(f"/api/v1/clips/{clip_id}/behavior", json=payload)
    assert first.status_code == second.status_code == 202
    event = asyncio.run(fetch_one(
        """SELECT event_key,client_session_id,context_json FROM clip_behavior_events
           WHERE clip_id=? AND event_type='impression'""",
        (clip_id,),
    ))
    assert event
    assert "creator@example.com" not in event["event_key"]
    assert "creator@example.com" not in (event["client_session_id"] or "")
    assert len(event["client_session_id"]) == 64
    assert json.loads(event["context_json"]) == {"surface": "project"}
    count = asyncio.run(fetch_one(
        "SELECT COUNT(*) count FROM clip_behavior_events WHERE clip_id=? AND event_type='impression'",
        (clip_id,),
    ))
    assert count["count"] == 1

    injected = client.post(
        f"/api/v1/clips/{clip_id}/behavior",
        json={**payload, "client_event_id": "different-event-id", "transcript": "do not store me"},
    )
    assert injected.status_code == 422
    invalid_field = client.post(
        f"/api/v1/clips/{clip_id}/behavior",
        json={
            "event_type": "edited", "client_event_id": "edit-event-1234",
            "client_session_id": "page-session-1", "surface": "editor",
            "changed_fields": ["email"],
        },
    )
    assert invalid_field.status_code == 422

    client.post("/api/v1/auth/logout")
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Other Creator", "email": "other-learning@example.com", "password": "Secure123"},
    )
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    denied = client.post(
        f"/api/v1/clips/{clip_id}/behavior",
        json={**payload, "client_event_id": "other-user-event"},
    )
    assert denied.status_code == 404


def test_export_lifecycle_and_download_create_strong_server_labels(client: TestClient) -> None:
    login_demo(client)
    project_id, clips = create_suggestions(client)
    attach_ranking_provenance(project_id)
    clip_id = clips[0]["id"]
    impression = client.post(
        f"/api/v1/clips/{clip_id}/behavior",
        json={
            "event_type": "impression", "client_event_id": "export-flow-impression",
            "client_session_id": "export-flow", "surface": "project",
        },
    )
    assert impression.status_code == 202
    with patch("app.api.routes._render_export", new=AsyncMock()):
        export = client.post(
            f"/api/v1/clips/{clip_id}/export",
            json={"resolution": "1080p", "watermark": False},
        )
    assert export.status_code == 202
    export_id = export.json()["id"]
    requested = asyncio.run(fetch_one(
        "SELECT source FROM clip_behavior_events WHERE event_key=?",
        (f"server:export_requested:{export_id}",),
    ))
    assert requested == {"source": "server"}

    asyncio.run(execute("UPDATE exports SET status='ready',progress=100 WHERE id=?", (export_id,)))
    asyncio.run(execute("UPDATE exports SET status='ready',progress=100 WHERE id=?", (export_id,)))
    ready_count = asyncio.run(fetch_one(
        "SELECT COUNT(*) count FROM clip_behavior_events WHERE event_key=?",
        (f"server:export_ready:{export_id}",),
    ))
    assert ready_count["count"] == 1
    downloaded = client.post(f"/api/v1/exports/{export_id}/download-event", json={})
    assert downloaded.status_code == 204

    rows = asyncio.run(learning_rows())
    row = next(item for item in rows if item["events"].get("downloaded"))
    assert row["label_strength"] == 5
    assert row["observed"] is True
    assert row["provenance_ready"] is True
    assert row["training_eligible"] is True
    assert row["eligible_negative"] is False


def test_export_failure_is_not_mislabeled_as_creator_rejection(client: TestClient) -> None:
    login_demo(client)
    project_id, clips = create_suggestions(client)
    attach_ranking_provenance(project_id)
    clip_id = clips[0]["id"]
    with patch("app.api.routes._render_export", new=AsyncMock()):
        export = client.post(
            f"/api/v1/clips/{clip_id}/export",
            json={"resolution": "1080p", "watermark": False},
        )
    assert export.status_code == 202
    export_id = export.json()["id"]
    asyncio.run(execute("UPDATE exports SET status='failed',error='worker unavailable' WHERE id=?", (export_id,)))
    rows = asyncio.run(learning_rows())
    row = next(item for item in rows if item["events"].get("export_failed"))
    assert row["events"]["export_requested"] == 1
    assert row["events"]["export_failed"] == 1
    assert row["label_strength"] == 4
    assert row["training_eligible"] is True
    assert row["eligible_negative"] is False


def test_unexposed_is_not_negative_and_reprocessing_preserves_generations(client: TestClient) -> None:
    login_demo(client)
    project_id, first_clips = create_suggestions(client)
    first_generation = asyncio.run(fetch_one(
        "SELECT id FROM recommendation_generations WHERE project_id=? ORDER BY created_at LIMIT 1",
        (project_id,),
    ))["id"]
    first_rows = asyncio.run(learning_rows())
    untouched = next(row for row in first_rows if row["generation_id"] == first_generation)
    assert untouched["observed"] is False
    assert untouched["eligible_negative"] is False
    assert untouched["label_strength"] is None
    assert untouched["training_eligible"] is False

    attach_ranking_provenance(project_id)
    exposed = client.post(
        f"/api/v1/clips/{first_clips[0]['id']}/behavior",
        json={
            "event_type": "impression", "client_event_id": "negative-after-exposure",
            "client_session_id": "negative-session", "surface": "project",
        },
    )
    assert exposed.status_code == 202
    rows_after_exposure = asyncio.run(learning_rows())
    negative = next(
        row for row in rows_after_exposure
        if row["generation_id"] == first_generation and row["suggestion_rank"] == 1
    )
    assert negative["label_strength"] == 0
    assert negative["eligible_negative"] is True
    assert negative["training_eligible"] is True

    second = client.post(
        f"/api/v1/projects/{project_id}/analyse",
        json={"language": "en", "segments": [
            {"start": 0, "end": 22, "text": "What if the strongest hook is the result before the explanation?"},
            {"start": 22, "end": 45, "text": "Show one concrete example, then explain the reason it works."},
            {"start": 45, "end": 70, "text": "The final takeaway is short, clear and complete for a new viewer."},
        ]},
    )
    assert second.status_code == 200 and second.json()
    generations = asyncio.run(fetch_all(
        "SELECT id FROM recommendation_generations WHERE project_id=? ORDER BY created_at",
        (project_id,),
    ))
    assert len(generations) == 2
    assert first_generation in {row["id"] for row in generations}
    assert not any(clip["id"] in {item["id"] for item in second.json()} for clip in first_clips)

    rows = asyncio.run(learning_rows())
    assert {row["generation_id"] for row in rows} == {row["id"] for row in generations}


def test_privacy_export_contains_learning_data_and_project_delete_cascades(client: TestClient) -> None:
    login_demo(client)
    project_id, clips = create_suggestions(client)
    response = client.post(
        f"/api/v1/clips/{clips[0]['id']}/behavior",
        json={
            "event_type": "preview_started", "client_event_id": "privacy-preview-event",
            "client_session_id": "privacy-session", "surface": "project",
        },
    )
    assert response.status_code == 202
    exported = client.get("/api/v1/privacy/export")
    assert exported.status_code == 200
    learning = exported.json()["behavioral_learning"]
    assert learning["recommendation_generations"]
    assert learning["suggestion_snapshots"]
    assert learning["events"]
    assert all("password" not in json.dumps(item).lower() for item in learning["events"])

    asyncio.run(execute("DELETE FROM projects WHERE id=?", (project_id,)))
    assert asyncio.run(fetch_one(
        "SELECT COUNT(*) count FROM recommendation_generations WHERE project_id=?", (project_id,)
    ))["count"] == 0
    assert asyncio.run(fetch_one(
        "SELECT COUNT(*) count FROM clip_behavior_events WHERE project_id=?", (project_id,)
    ))["count"] == 0


def test_offline_export_script_compiles() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "export_behavioral_learning.py"
    compile(script.read_text(encoding="utf-8"), str(script), "exec")

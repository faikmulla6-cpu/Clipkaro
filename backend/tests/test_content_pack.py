from unittest.mock import AsyncMock, patch
import asyncio
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import fetch_all, fetch_one
from app.main import app
from app.services.content_pack import generate_content_pack, validate_content_pack
from app.services.legal import LEGAL_VERSION


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
        "allow_manual_analysis_in_development": settings.allow_manual_analysis_in_development,
    }
    settings.database_path = tmp_path / "content-pack.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = True
    settings.app_env = "test"
    settings.allow_manual_analysis_in_development = True
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def login_demo(client: TestClient):
    response = client.post("/api/v1/auth/login", json={"email": "demo@clipkaro.ai", "password": "ClipKaro123!"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post("/api/v1/legal/accept", json={"accepted": True, "version": LEGAL_VERSION})
    assert accepted.status_code == 200


def ready_project(client: TestClient, *, category: str = "comedy", language: str = "hinglish") -> tuple[str, list[dict]]:
    with patch("app.api.routes._process_project", new=AsyncMock()):
        upload = client.post(
            "/api/v1/projects/upload",
            data={"title": "Bassi engineering crowd work", "language": language, "category": category},
            files={"file": ("source.mp4", b"test-bytes", "video/mp4")},
        )
    assert upload.status_code == 201
    project_id = upload.json()["id"]
    segments = [
        {"start": 0, "end": 24, "text": "Bhai placement ke time sab serious ho jaate hain aur attendance ka scene alag hota hai."},
        {"start": 24, "end": 51, "text": "The joke works because every engineering student has seen that confusion in real life."},
        {"start": 51, "end": 78, "text": "Nobody knows the full plan but everyone has an explanation ready for viva."},
    ]
    analysis = client.post(f"/api/v1/projects/{project_id}/analyse", json={"language": language, "segments": segments})
    assert analysis.status_code == 200
    return project_id, analysis.json()


def test_content_pack_generation_success_persists_and_is_idempotent(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    first = client.post(f"/api/v1/projects/{project_id}/content-pack")
    second = client.post(f"/api/v1/projects/{project_id}/content-pack")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["content_pack"] == second.json()["content_pack"]
    rows = asyncio.run(fetch_all("SELECT * FROM content_packs WHERE project_id=?", (project_id,)))
    assert len(rows) == 1 and rows[0]["status"] == "ready"


def test_content_pack_authorization_is_project_scoped(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    client.post("/api/v1/auth/logout")
    signup = client.post("/api/v1/auth/signup", json={"name": "Other User", "email": "other-pack@example.com", "password": "Secure123"})
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    assert client.get(f"/api/v1/projects/{project_id}/content-pack").status_code == 404
    assert client.post(f"/api/v1/projects/{project_id}/content-pack").status_code == 404


def test_old_project_without_content_pack_returns_missing(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    response = client.get(f"/api/v1/projects/{project_id}/content-pack")
    assert response.status_code == 200
    assert response.json()["status"] == "missing"


def test_provider_failure_is_recoverable_and_persisted(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    with patch("app.api.worker_jobs.generate_content_pack", side_effect=RuntimeError("provider timeout")):
        response = client.post(f"/api/v1/projects/{project_id}/content-pack")
    assert response.status_code == 502
    row = asyncio.run(fetch_one("SELECT status FROM content_packs WHERE project_id=?", (project_id,)))
    assert row and row["status"] == "failed"


def test_malformed_content_pack_response_is_rejected():
    with pytest.raises(ValueError):
        validate_content_pack({"clips": [{"youtube_shorts": {"titles": ["same"]}}]})


def test_hinglish_content_pack_preserves_tone(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    response = client.post(f"/api/v1/projects/{project_id}/content-pack")
    pack = response.json()["content_pack"]
    text = " ".join(pack["clips"][0]["youtube_shorts"]["titles"] + [pack["clips"][0]["instagram_reels"]["caption"]]).casefold()
    assert "bhai" in text or "scene" in text
    assert "in today's fast-paced world" not in text


def test_irrelevant_linkedin_is_suppressed_for_pure_comedy():
    project = {"id": "project-1", "title": "Comedy crowd work", "category": "comedy"}
    clips = [{
        "id": "clip-1", "title": "Chai joke", "hook": "Bhai chai gir gayi aur sab hasne lage",
        "reason": "Funny standalone moment", "transcript_text": "Bhai chai gir gayi aur sab hasne lage",
        "score": 80, "score_breakdown": {"hook": 70},
    }]
    segments = [{"start": 0, "end": 24, "text": "Bhai chai gir gayi aur sab hasne lage"}]
    pack = generate_content_pack(project, clips, segments, "hinglish")
    assert pack["clips"][0]["linkedin"]["recommended"] is False
    assert pack["clips"][0]["linkedin"]["post"] == "Not recommended for this clip"

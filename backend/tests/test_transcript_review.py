from unittest.mock import AsyncMock, patch
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.main import app
from app.schemas.api import ExportRequest
from app.api import routes
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
    settings.database_path = tmp_path / "transcript-review.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret-for-transcript-review"
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


def ready_project(client: TestClient) -> tuple[str, list[dict]]:
    with patch("app.api.routes._process_project", new=AsyncMock()):
        upload = client.post(
            "/api/v1/projects/upload",
            data={"title": "Transcript review QA", "language": "hinglish", "category": "comedy"},
            files={"file": ("source.mp4", b"test-bytes", "video/mp4")},
        )
    assert upload.status_code == 201
    project_id = upload.json()["id"]
    segments = [
        {"start": 0, "end": 24, "text": "placement placement placement placement thyme sab serious ho jate he"},
        {"start": 24, "end": 51, "text": "bhai group project me jugaad aur viva explanation ready hota hai"},
        {"start": 51, "end": 78, "text": "deadline ke pehle ka pressure sabko samajh aata hai"},
    ]
    analysis = client.post(f"/api/v1/projects/{project_id}/analyse", json={"language": "hinglish", "segments": segments})
    assert analysis.status_code == 200
    return project_id, analysis.json()


def test_transcript_review_read_save_persist_caption_and_content_pack_regenerate(client: TestClient):
    login_demo(client)
    project_id, clips = ready_project(client)
    created = client.post(f"/api/v1/projects/{project_id}/content-pack")
    assert created.status_code == 201

    review = client.get(f"/api/v1/projects/{project_id}/transcript-review")
    assert review.status_code == 200
    flagged = review.json()["segments"][0]
    assert flagged["index"] == 0
    assert flagged["start"] == 0 and flagged["end"] == 24
    assert "Possible repeated words" in flagged["reasons"]

    correction = "placement ke time sab serious ho jaate hain"
    saved = client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": correction})
    assert saved.status_code == 200
    assert saved.json()["text"] == correction

    refreshed = client.get(f"/api/v1/projects/{project_id}/transcript-review").json()
    corrected = next(item for item in refreshed["segments"] if item["index"] == 0)
    assert corrected["state"] == "corrected"
    assert corrected["text"] == correction
    assert refreshed["summary"]["corrected"] == 1
    assert refreshed["summary"]["remaining"] == 0

    rows = asyncio.run(fetch_all("SELECT * FROM transcript_corrections WHERE project_id=?", (project_id,)))
    assert len(rows) == 1
    assert rows[0]["original_text"] == "placement placement placement placement thyme sab serious ho jate he"
    transcript = asyncio.run(fetch_one(
        """SELECT t.* FROM transcripts t JOIN videos v ON v.id=t.video_id WHERE v.project_id=?""",
        (project_id,),
    ))
    source_segments = json.loads(transcript["segments_json"])
    assert source_segments[0]["text"] == "placement placement placement placement thyme sab serious ho jate he"

    clip = next(item for item in client.get(f"/api/v1/projects/{project_id}").json()["clips"] if correction in item["transcript_text"])
    captions = client.get(f"/api/v1/clips/{clip['id']}/captions").json()
    assert "jaate" in " ".join(word["text"] for word in captions["words"])

    stale = client.get(f"/api/v1/projects/{project_id}/content-pack").json()
    assert stale["status"] == "stale"
    regenerated = client.post(f"/api/v1/projects/{project_id}/content-pack")
    assert regenerated.status_code == 201
    pack_text = json.dumps(regenerated.json()["content_pack"], ensure_ascii=False)
    assert "jaate hain" in pack_text


def test_project_detail_resolves_effective_clip_snippet_after_save(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    correction = "placement ke time sab serious ho jaate hain"
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": correction}).status_code == 200
    detail = client.get(f"/api/v1/projects/{project_id}").json()
    assert any(correction in clip["transcript_text"] for clip in detail["clips"])


def test_project_detail_resolves_visible_hook_from_corrected_transcript(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    correction = "placement ke time sab serious ho jaate hain"
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": correction}).status_code == 200
    asyncio.run(execute(
        """UPDATE clips SET hook='Bhai Bass Karr Bhaii injeenering acchee meree caahate hue'
           WHERE video_id=(SELECT id FROM videos WHERE project_id=?)""",
        (project_id,),
    ))

    detail = client.get(f"/api/v1/projects/{project_id}").json()
    corrected_clip = next(clip for clip in detail["clips"] if correction in clip["transcript_text"])
    assert corrected_clip["hook"].startswith("placement ke time sab serious")
    assert "injeenering" not in corrected_clip["hook"]
    assert "caahate" not in corrected_clip["hook"]


def test_project_detail_avoids_uncorrected_noisy_visible_hook(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    transcript = asyncio.run(fetch_one(
        """SELECT t.* FROM transcripts t JOIN videos v ON v.id=t.video_id WHERE v.project_id=?""",
        (project_id,),
    ))
    segments = json.loads(transcript["segments_json"])
    segments[0]["text"] = "ki ab yah laait kiyaa landan aa gayaa ab baahar rahate ho tabhee ham"
    segments[0]["display_text"] = segments[0]["text"]
    asyncio.run(execute(
        """UPDATE transcripts SET segments_json=? WHERE video_id=(SELECT id FROM videos WHERE project_id=?)""",
        (json.dumps(segments), project_id),
    ))
    asyncio.run(execute(
        """UPDATE clips SET hook='ki ab yah laait kiyaa landan aa gayaa ab baahar rahate ho tabhee ham',
           start_time=0,end_time=24 WHERE video_id=(SELECT id FROM videos WHERE project_id=?)""",
        (project_id,),
    ))

    detail = client.get(f"/api/v1/projects/{project_id}").json()
    noisy_clip = detail["clips"][0]
    assert noisy_clip["hook"] == "Transcript needs review"
    assert "laait" not in noisy_clip["hook"]
    assert "landan" not in noisy_clip["hook"]


def test_export_render_uses_effective_corrected_caption_text(client: TestClient, tmp_path):
    login_demo(client)
    project_id, _ = ready_project(client)
    correction = "placement ke time sab serious ho jaate hain"
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": correction}).status_code == 200
    clip = next(item for item in client.get(f"/api/v1/projects/{project_id}").json()["clips"] if correction in item["transcript_text"])
    db_clip = asyncio.run(fetch_one("SELECT c.*,p.user_id FROM clips c JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id WHERE c.id=?", (clip["id"],)))
    video = asyncio.run(fetch_one("SELECT * FROM videos WHERE id=?", (db_clip["video_id"],)))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake-video")
    output = tmp_path / "output.mp4"
    captured = {}

    async def fake_render(*args, **kwargs):
        srt = args[4]
        captured["srt"] = srt.read_text(encoding="utf-8") if srt else ""
        output.write_bytes(b"rendered")

    async def fake_scan(*args, **kwargs):
        return {"detected": False, "confidence": 0}

    with patch.object(routes, "render_short_limited", new=fake_render), patch.object(routes, "detect_burned_captions", new=fake_scan):
        asyncio.run(routes._render_export("job-corrected", "export-corrected", db_clip, video, ExportRequest(), output, None, source_override=source))

    assert "jaate" in captured["srt"]
    assert "thyme" not in captured["srt"]


def test_export_render_can_disable_hook_overlay(client: TestClient, tmp_path):
    login_demo(client)
    project_id, _ = ready_project(client)
    clip = client.get(f"/api/v1/projects/{project_id}").json()["clips"][0]
    db_clip = asyncio.run(fetch_one(
        "SELECT c.*,p.user_id FROM clips c JOIN videos v ON v.id=c.video_id "
        "JOIN projects p ON p.id=v.project_id WHERE c.id=?",
        (clip["id"],),
    ))
    video = asyncio.run(fetch_one("SELECT * FROM videos WHERE id=?", (db_clip["video_id"],)))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake-video")
    output = tmp_path / "output.mp4"
    captured = {}

    async def fake_render(*args, **kwargs):
        captured["hook"] = args[5]
        output.write_bytes(b"rendered")

    async def fake_scan(*args, **kwargs):
        return {"detected": False, "confidence": 0}

    request = ExportRequest(hook_text="Keep this text for later", hook_enabled=False)
    with patch.object(routes, "render_short_limited", new=fake_render), patch.object(routes, "detect_burned_captions", new=fake_scan):
        asyncio.run(routes._render_export(
            "job-hook-off", "export-hook-off", db_clip, video, request, output, None,
            source_override=source,
        ))

    assert captured["hook"] == ""


def test_transcript_review_reset_restores_original_and_preserves_timestamps(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    correction = "bhai ye kya scene hai samajh nahi aaya jugaad"
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": correction}).status_code == 200
    reset = client.delete(f"/api/v1/projects/{project_id}/transcript-review/0")
    assert reset.status_code == 200
    assert reset.json()["text"] == "placement placement placement placement thyme sab serious ho jate he"
    review = client.get(f"/api/v1/projects/{project_id}/transcript-review").json()
    segment = next(item for item in review["segments"] if item["index"] == 0)
    assert segment["state"] == "needs_review"
    assert segment["start"] == 0 and segment["end"] == 24
    assert segment["text"] == "placement placement placement placement thyme sab serious ho jate he"
    assert asyncio.run(fetch_one("SELECT id FROM transcript_corrections WHERE project_id=?", (project_id,))) is None


def test_transcript_review_authorization_and_malformed_requests(client: TestClient):
    login_demo(client)
    project_id, _ = ready_project(client)
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/999", json={"text": "valid text"}).status_code == 404
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": ""}).status_code == 422

    client.post("/api/v1/auth/logout")
    signup = client.post("/api/v1/auth/signup", json={"name": "Other User", "email": "other-review@example.com", "password": "Secure123"})
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    assert client.get(f"/api/v1/projects/{project_id}/transcript-review").status_code == 404
    assert client.patch(f"/api/v1/projects/{project_id}/transcript-review/0", json={"text": "stolen edit"}).status_code == 404
    assert client.delete(f"/api/v1/projects/{project_id}/transcript-review/0").status_code == 404

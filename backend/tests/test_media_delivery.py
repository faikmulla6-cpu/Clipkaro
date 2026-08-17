import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import fetch_one
from app.main import app
from app.services.auth import create_token
from app.services.media_delivery import (
    MediaAsset,
    MediaToolUnavailable,
    StreamProfile,
    ensure_browser_media,
    preview_path_for,
    probe_stream_profile,
    remove_orphaned_previews,
    source_media_type,
)
from app.services.render_gate import media_encode_slot, render_short_limited
from app.services.video import upload_type_supported


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    settings.database_path = tmp_path / "media-test.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "unit-test-secret"
    settings.seed_demo_user = True
    with TestClient(app) as test_client:
        yield test_client


def login_demo(client: TestClient) -> None:
    """Authenticate fixtures without consuming the real login abuse budget."""
    csrf = "media-test-csrf"
    # Scope fixture cookies exactly like TestClient response cookies. That lets
    # the real logout/signup flows replace them instead of creating duplicate
    # same-name cookies with different domains.
    client.cookies.set("access_token", create_token("demo-user"), domain="testserver.local", path="/")
    client.cookies.set("csrf_token", csrf, domain="testserver.local", path="/")
    client.headers["X-CSRF-Token"] = csrf


def upload_without_processing(client: TestClient, filename: str, payload: bytes, mime: str) -> dict:
    with patch("app.api.routes._process_project", new=AsyncMock()):
        response = client.post(
            "/api/v1/projects/upload",
            data={"title": filename},
            files={"file": (filename, payload, mime)},
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_source_mime_mapping_is_truthful_and_unknown_is_not_fake_mp4(tmp_path):
    assert source_media_type("clip.mp4", tmp_path / "clip.mp4") == "video/mp4"
    assert source_media_type("clip.MOV", tmp_path / "clip.MOV") == "video/quicktime"
    assert source_media_type("clip.webm", tmp_path / "clip.webm") == "video/webm"
    assert source_media_type("clip.mkv", tmp_path / "clip.mkv") == "video/x-matroska"
    assert source_media_type("clip.mov", tmp_path / "migrated.mp4") == "video/mp4"
    assert source_media_type("legacy.webm", tmp_path / "blob") == "video/webm"
    assert source_media_type("mystery.bin", tmp_path / "mystery.bin") == "application/octet-stream"


def test_upload_validation_accepts_generic_browser_mime_for_known_video_extension():
    assert upload_type_supported("camera.mp4", "video/mp4")
    assert upload_type_supported("camera.mov", "video/quicktime")
    assert upload_type_supported("camera.webm", "video/webm")
    assert upload_type_supported("camera.mkv", "video/x-matroska")
    assert upload_type_supported("camera.mkv", "video/matroska")
    assert upload_type_supported("camera.mkv", "application/octet-stream")
    assert upload_type_supported("camera.mkv", "application/x-matroska")
    assert upload_type_supported("camera.mkv", "application/matroska")
    assert upload_type_supported("camera.MOV", "")
    assert not upload_type_supported("camera.exe", "video/mp4")
    assert not upload_type_supported("camera.jpg", "image/jpeg")
    assert not upload_type_supported("camera.mp4", "image/jpeg")


@pytest.mark.parametrize(
    ("filename", "mime"),
    [
        ("source.mp4", "video/mp4"),
        ("source.mov", "video/quicktime"),
        ("source.webm", "video/webm"),
        ("source.mkv", "video/x-matroska"),
    ],
)
def test_original_media_route_returns_correct_mime(client: TestClient, filename: str, mime: str):
    login_demo(client)
    project = upload_without_processing(client, filename, b"0123456789abcdef", mime)
    response = client.get(f"/api/v1/projects/{project['id']}/media/original")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";", 1)[0] == mime
    assert response.headers["x-clipkaro-media-mode"] == "original"
    assert response.headers["x-clipkaro-source-media-type"] == mime
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == b"0123456789abcdef"


def test_browser_media_route_preserves_range_seek_and_asset_mime(client: TestClient):
    login_demo(client)
    project = upload_without_processing(client, "seek.webm", b"0123456789abcdef", "video/webm")
    video = asyncio.run(fetch_one("SELECT * FROM videos WHERE id=?", (project["video_id"],)))
    assert video
    asset = MediaAsset(Path(video["file_path"]), "video/webm", "direct")
    with patch("app.api.media.ensure_browser_media", new=AsyncMock(return_value=asset)):
        response = client.get(
            f"/api/v1/projects/{project['id']}/media",
            headers={"Range": "bytes=4-9"},
        )
    assert response.status_code == 206
    assert response.content == b"456789"
    assert response.headers["content-type"].split(";", 1)[0] == "video/webm"
    assert response.headers["content-range"] == "bytes 4-9/16"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-clipkaro-media-mode"] == "direct"


def test_media_routes_do_not_leak_other_users_private_video(client: TestClient):
    login_demo(client)
    project = upload_without_processing(client, "private.mov", b"private", "video/quicktime")
    client.post("/api/v1/auth/logout")
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Other", "email": "media-other@example.com", "password": "Secure123"},
    )
    assert signup.status_code == 201
    client.headers["X-CSRF-Token"] = client.cookies.get(
        "csrf_token", domain="testserver.local", path="/"
    )
    assert client.get(f"/api/v1/projects/{project['id']}/media").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/media/original").status_code == 404


def test_media_routes_fail_closed_when_retained_source_is_missing(client: TestClient):
    login_demo(client)
    project = upload_without_processing(client, "expired.mp4", b"gone", "video/mp4")
    video = asyncio.run(fetch_one("SELECT * FROM videos WHERE id=?", (project["video_id"],)))
    assert video
    Path(video["file_path"]).unlink()
    assert client.get(f"/api/v1/projects/{project['id']}/media").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/media/original").status_code == 404


def test_corrupt_source_remains_truthful_original_but_browser_preview_fails_cleanly(client: TestClient):
    login_demo(client)
    payload = b"not-a-real-quicktime-file"
    project = upload_without_processing(client, "corrupt.mov", payload, "video/quicktime")
    original = client.get(f"/api/v1/projects/{project['id']}/media/original")
    preview = client.get(f"/api/v1/projects/{project['id']}/media")
    assert original.status_code == 200
    assert original.headers["content-type"].split(";", 1)[0] == "video/quicktime"
    assert original.content == payload
    assert preview.status_code == 422
    assert "browser-compatible preview" in preview.json()["detail"]


def test_media_engine_unavailable_returns_service_unavailable(client: TestClient):
    login_demo(client)
    project = upload_without_processing(client, "engine.mov", b"source", "video/quicktime")
    with patch(
        "app.api.media.ensure_browser_media",
        new=AsyncMock(side_effect=MediaToolUnavailable("ffmpeg missing")),
    ):
        response = client.get(f"/api/v1/projects/{project['id']}/media")
    assert response.status_code == 503
    assert "media engine" in response.json()["detail"]


def test_concurrent_preview_requests_build_one_cached_proxy(tmp_path, monkeypatch):
    settings = get_settings()
    original_root = settings.storage_root
    settings.storage_root = tmp_path / "storage"
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    video = {"id": "same-video", "file_path": str(source), "original_filename": "source.mkv"}
    builds = 0

    async def fake_probe(_path: Path) -> StreamProfile:
        return StreamProfile("h264", None, "matroska")

    async def fake_build(_source: Path, destination: Path, _profile: StreamProfile) -> None:
        nonlocal builds
        builds += 1
        await asyncio.sleep(0.04)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"proxy")

    monkeypatch.setattr("app.services.media_delivery.probe_stream_profile", fake_probe)
    monkeypatch.setattr("app.services.media_delivery._build_mp4_proxy", fake_build)

    async def compete():
        return await asyncio.gather(*(ensure_browser_media(video) for _ in range(8)))

    try:
        assets = asyncio.run(compete())
        assert builds == 1
        assert all(asset.path == preview_path_for("same-video") for asset in assets)
        assert all(asset.media_type == "video/mp4" for asset in assets)
        assert {asset.mode for asset in assets} <= {"transcoded-proxy", "cached-proxy"}
    finally:
        settings.storage_root = original_root


def test_shared_ffmpeg_gate_serializes_export_and_preview_consumers(monkeypatch):
    settings = get_settings()
    original_limit = settings.render_concurrency
    settings.render_concurrency = 1
    active = 0
    maximum = 0

    async def work() -> None:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.04)
        active -= 1

    async def fake_render(*_args, **_kwargs) -> None:
        await work()

    monkeypatch.setattr("app.services.render_gate.render_short", fake_render)

    async def preview_consumer() -> None:
        async with media_encode_slot():
            await work()

    async def scenario() -> None:
        await asyncio.gather(render_short_limited(), preview_consumer())

    try:
        asyncio.run(scenario())
        assert maximum == 1
    finally:
        settings.render_concurrency = original_limit


def test_orphaned_preview_cache_is_removed_without_touching_live_preview(tmp_path):
    settings = get_settings()
    original_root = settings.storage_root
    settings.storage_root = tmp_path / "storage"
    try:
        live = preview_path_for("live-video")
        orphan = preview_path_for("deleted-video")
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_bytes(b"live")
        orphan.write_bytes(b"orphan")
        assert remove_orphaned_previews({"live-video"}) == 1
        assert live.exists()
        assert not orphan.exists()
    finally:
        settings.storage_root = original_root


def _generate_video(path: Path, codec: str, audio_codec: str | None = None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is unavailable")
    command = [
        ffmpeg, "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=black:s=160x90:d=0.35",
    ]
    if audio_codec:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.35"]
    command += ["-pix_fmt", "yuv420p", "-c:v", codec]
    if codec == "libx264":
        command += ["-preset", "ultrafast"]
    if audio_codec:
        command += ["-c:a", audio_codec, "-shortest"]
    else:
        command += ["-an"]
    command.append(str(path))
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30)
    if proc.returncode != 0:
        pytest.skip(
            f"FFmpeg codec/container combination {codec}/{audio_codec or 'no-audio'} unavailable: "
            f"{proc.stderr.decode(errors='ignore')[-200:]}"
        )


def test_real_mov_proxy_is_mp4_cached_and_seekable(client: TestClient, tmp_path):
    login_demo(client)
    source = tmp_path / "browser.mov"
    _generate_video(source, "libx264")
    project = upload_without_processing(client, source.name, source.read_bytes(), "video/quicktime")

    first = client.get(f"/api/v1/projects/{project['id']}/media")
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].split(";", 1)[0] == "video/mp4"
    assert first.headers["x-clipkaro-source-media-type"] == "video/quicktime"
    assert first.headers["x-clipkaro-media-mode"] == "transcoded-proxy"
    assert len(first.content) > 100

    second = client.get(f"/api/v1/projects/{project['id']}/media", headers={"Range": "bytes=0-31"})
    assert second.status_code == 206
    assert second.headers["content-type"].split(";", 1)[0] == "video/mp4"
    assert second.headers["x-clipkaro-media-mode"] == "cached-proxy"
    assert second.headers["content-range"].startswith("bytes 0-31/")
    assert len(second.content) == 32


def test_real_h264_mkv_is_normalized_to_mp4_with_truthful_source_type(client: TestClient, tmp_path):
    login_demo(client)
    source = tmp_path / "browser.mkv"
    _generate_video(source, "libx264")
    project = upload_without_processing(client, source.name, source.read_bytes(), "application/x-matroska")

    response = client.get(f"/api/v1/projects/{project['id']}/media")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].split(";", 1)[0] == "video/mp4"
    assert response.headers["x-clipkaro-source-media-type"] == "video/x-matroska"
    assert response.headers["x-clipkaro-media-mode"] == "transcoded-proxy"


def test_real_incompatible_mov_video_codec_is_reencoded_to_h264(client: TestClient, tmp_path):
    login_demo(client)
    source = tmp_path / "mpeg4.mov"
    _generate_video(source, "mpeg4")
    project = upload_without_processing(client, source.name, source.read_bytes(), "video/quicktime")

    response = client.get(f"/api/v1/projects/{project['id']}/media")
    assert response.status_code == 200, response.text
    video = asyncio.run(fetch_one("SELECT * FROM videos WHERE id=?", (project["video_id"],)))
    assert video
    output = preview_path_for(str(video["id"]))
    profile = asyncio.run(probe_stream_profile(output))
    assert profile.video_codec == "h264"
    assert response.headers["content-type"].split(";", 1)[0] == "video/mp4"


def test_real_incompatible_mov_audio_is_reencoded_to_aac(client: TestClient, tmp_path):
    login_demo(client)
    source = tmp_path / "pcm.mov"
    _generate_video(source, "libx264", "pcm_s16le")
    project = upload_without_processing(client, source.name, source.read_bytes(), "video/quicktime")

    response = client.get(f"/api/v1/projects/{project['id']}/media")
    assert response.status_code == 200, response.text
    video = asyncio.run(fetch_one("SELECT * FROM videos WHERE id=?", (project["video_id"],)))
    assert video
    profile = asyncio.run(probe_stream_profile(preview_path_for(str(video["id"]))))
    assert profile.video_codec == "h264"
    assert profile.audio_codec == "aac"


def test_real_browser_safe_mp4_is_not_needlessly_transcoded(client: TestClient, tmp_path):
    login_demo(client)
    source = tmp_path / "browser.mp4"
    _generate_video(source, "libx264")
    project = upload_without_processing(client, source.name, source.read_bytes(), "video/mp4")

    response = client.get(f"/api/v1/projects/{project['id']}/media")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";", 1)[0] == "video/mp4"
    assert response.headers["x-clipkaro-media-mode"] == "direct"
    assert response.headers["x-clipkaro-source-media-type"] == "video/mp4"

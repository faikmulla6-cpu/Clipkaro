from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.services.youtube_import as youtube_import
from app.api.cloud_uploads import _reject_if_youtube_import_active
from app.services.youtube_import import (
    YouTubeImportError,
    canonicalize_youtube_url,
    download_youtube_source,
)


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=10", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_youtube_urls_are_canonicalized(url: str, video_id: str) -> None:
    canonical, parsed_id = canonicalize_youtube_url(url)
    assert parsed_id == video_id
    assert canonical == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "http://127.0.0.1/watch?v=dQw4w9WgXcQ",
        "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
        "https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com:8443/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/playlist?list=PL123",
        "file:///etc/passwd",
    ],
)
def test_youtube_import_rejects_non_video_or_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        canonicalize_youtube_url(url)


class _FakeYoutubeDL:
    calls: list[dict] = []

    def __init__(self, options: dict) -> None:
        self.options = options
        self.__class__.calls.append(options)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        info = {"id": "dQw4w9WgXcQ", "title": "  Creator   lesson  ", "duration": 120.0, "is_live": False}
        if download:
            target = Path(self.options["outtmpl"].replace("%(ext)s", "mp4"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"clipkaro-test-media")
        return info


def test_download_is_single_video_bounded_and_uses_scratch(monkeypatch, tmp_path: Path) -> None:
    _FakeYoutubeDL.calls.clear()
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=_FakeYoutubeDL))
    result = download_youtube_source(
        "https://youtu.be/dQw4w9WgXcQ",
        tmp_path,
        max_minutes=15,
        remaining_minutes=15,
        max_bytes=1024,
    )
    assert result.path == tmp_path / "source.mp4"
    assert result.title == "Creator lesson"
    assert result.duration == 120.0
    assert len(_FakeYoutubeDL.calls) == 2
    download_options = _FakeYoutubeDL.calls[-1]
    assert download_options["noplaylist"] is True
    assert download_options["max_filesize"] == 1024
    assert download_options["concurrent_fragment_downloads"] == 1


def test_duration_is_rejected_before_download(monkeypatch, tmp_path: Path) -> None:
    class LongVideoDL(_FakeYoutubeDL):
        def extract_info(self, url: str, download: bool = False) -> dict:
            if download:
                raise AssertionError("download must not start after duration rejection")
            return {"id": "dQw4w9WgXcQ", "title": "Long", "duration": 3600.0, "is_live": False}

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=LongVideoDL))
    with pytest.raises(YouTubeImportError, match="YOUTUBE_IMPORT_FAILED") as error:
        download_youtube_source(
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path,
            max_minutes=15,
            remaining_minutes=15,
            max_bytes=1024,
        )
    assert "15 minutes" in error.value.public_message


class _GuardCursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class _GuardDb:
    def __init__(self, row):
        self.row = row
        self.query = ""
        self.params = ()

    async def execute(self, query, params=()):
        self.query = query
        self.params = params
        return _GuardCursor(self.row)


def test_active_youtube_import_guard_blocks_duplicate_remote_work() -> None:
    db = _GuardDb({"id": "job-1"})
    with pytest.raises(HTTPException) as error:
        asyncio.run(_reject_if_youtube_import_active(db, "user-1"))
    assert getattr(error.value, "status_code", None) == 409
    assert "import_youtube" in db.query
    assert "queued" in db.query and "processing" in db.query
    assert db.params == ("user-1",)


def test_active_youtube_import_guard_allows_when_queue_is_clear() -> None:
    db = _GuardDb(None)
    asyncio.run(_reject_if_youtube_import_active(db, "user-2"))
    assert db.params == ("user-2",)


def test_youtube_bot_check_surfaces_no_charge_upload_fallback(monkeypatch, tmp_path: Path) -> None:
    class BlockedDL(_FakeYoutubeDL):
        def extract_info(self, url: str, download: bool = False) -> dict:
            raise RuntimeError("Sign in to confirm you're not a bot")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=BlockedDL))
    with pytest.raises(YouTubeImportError, match="YOUTUBE_IMPORT_FAILED") as error:
        download_youtube_source(
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path,
            max_minutes=15,
            remaining_minutes=15,
            max_bytes=1024,
        )
    assert "Karo Minutes were not charged" in error.value.public_message
    assert "Upload your original file instead" in error.value.public_message


def test_download_phase_bot_check_keeps_original_upload_fallback(monkeypatch, tmp_path: Path) -> None:
    class BlockedDownloadDL(_FakeYoutubeDL):
        def extract_info(self, url: str, download: bool = False) -> dict:
            if download:
                raise RuntimeError("Sign in to confirm you're not a bot")
            return super().extract_info(url, download=False)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=BlockedDownloadDL))
    with pytest.raises(YouTubeImportError, match="YOUTUBE_IMPORT_FAILED") as error:
        download_youtube_source(
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path,
            max_minutes=15,
            remaining_minutes=15,
            max_bytes=1024,
        )
    assert "YouTube blocked the secure server import" in error.value.public_message
    assert "Karo Minutes were not charged" in error.value.public_message
    assert "Upload your original file instead" in error.value.public_message


def test_vendored_ytdlp_matches_the_modal_and_ingestion_worker_builds() -> None:
    root = Path(__file__).resolve().parents[2]
    version = (root / "yt-dlp" / "yt_dlp" / "version.py").read_text(encoding="utf-8")
    backend_requirements = (root / "backend" / "requirements.txt").read_text(encoding="utf-8")
    worker_dockerfile = (root / "ingestion_worker" / "Dockerfile").read_text(encoding="utf-8")
    assert "__version__ = '2026.10.26'" in version
    assert "yt-dlp[default,deno]==2026.10.26" in backend_requirements
    assert "COPY yt-dlp /opt/yt-dlp-src" in worker_dockerfile
    assert "'/opt/yt-dlp-src[default]'" in worker_dockerfile


class _ProviderResponse:
    def __init__(self, payload=None, *, status_code=200, body=b"", headers=None):
        self._payload = payload
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise youtube_import.requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1024 * 1024):
        for index in range(0, len(self._body), chunk_size):
            yield self._body[index:index + chunk_size]

    def close(self):
        return None


class _SocialKitSession:
    instances = []

    def __init__(self):
        self.calls = []
        self.__class__.instances.append(self)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _ProviderResponse({"success": True, "data": {"jobId": "provider_job_123", "status": "queued"}})

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if "/v2/downloads/" in url:
            return _ProviderResponse({
                "success": True,
                "data": {
                    "jobId": "provider_job_123",
                    "status": "ready",
                    "downloadUrl": "https://socialkit-downloads.s3.amazonaws.com/source.mp4",
                    "durationSeconds": 120,
                    "fileSizeMB": "0.01 MB",
                    "title": "Provider creator lesson",
                },
            })
        return _ProviderResponse(body=b"provider-media-bytes", headers={"Content-Length": "20"})

    def close(self):
        return None


def test_auto_falls_back_to_provider_after_youtube_bot_block(monkeypatch, tmp_path: Path) -> None:
    class BlockedDL(_FakeYoutubeDL):
        def extract_info(self, url: str, download: bool = False) -> dict:
            raise RuntimeError("Sign in to confirm you're not a bot")

    _SocialKitSession.instances.clear()
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=BlockedDL))
    monkeypatch.setattr(youtube_import.requests, "Session", _SocialKitSession)

    result = download_youtube_source(
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        tmp_path,
        max_minutes=15,
        remaining_minutes=9,
        max_bytes=1024 * 1024,
        ingestion_provider="auto",
        socialkit_access_key="test-key",
        socialkit_poll_interval_seconds=0.01,
    )
    assert result.path == tmp_path / "source.mp4"
    assert result.path.read_bytes() == b"provider-media-bytes"
    assert result.title == "Provider creator lesson"
    assert result.duration == 120
    session = _SocialKitSession.instances[-1]
    post = next(call for call in session.calls if call[0] == "POST")
    assert post[2]["json"]["max_duration"] == 540
    assert "access_key" not in post[2]["json"]
    assert post[2]["headers"]["x-access-key"] == "test-key"


def test_provider_rejects_untrusted_download_host(monkeypatch, tmp_path: Path) -> None:
    class EvilSession(_SocialKitSession):
        def get(self, url, **kwargs):
            if "/v2/downloads/" in url:
                return _ProviderResponse({
                    "success": True,
                    "data": {
                        "jobId": "provider_job_123",
                        "status": "ready",
                        "downloadUrl": "https://127.0.0.1/private.mp4",
                        "durationSeconds": 60,
                        "fileSizeMB": "0.01 MB",
                        "title": "Unsafe",
                    },
                })
            raise AssertionError("untrusted URL must be rejected before download")

    monkeypatch.setattr(youtube_import.requests, "Session", EvilSession)
    with pytest.raises(YouTubeImportError, match="YOUTUBE_IMPORT_FAILED") as error:
        download_youtube_source(
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path,
            max_minutes=15,
            remaining_minutes=15,
            max_bytes=1024 * 1024,
            ingestion_provider="socialkit",
            socialkit_access_key="test-key",
            socialkit_poll_interval_seconds=0.01,
        )
    assert "untrusted media host" in error.value.public_message


def test_provider_duration_is_rechecked_before_media_download(monkeypatch, tmp_path: Path) -> None:
    class TooLongSession(_SocialKitSession):
        def get(self, url, **kwargs):
            if "/v2/downloads/" in url:
                return _ProviderResponse({
                    "success": True,
                    "data": {
                        "jobId": "provider_job_123",
                        "status": "ready",
                        "downloadUrl": "https://socialkit-downloads.s3.amazonaws.com/source.mp4",
                        "durationSeconds": 601,
                        "fileSizeMB": "1 MB",
                        "title": "Too long",
                    },
                })
            raise AssertionError("media download must not start after duration rejection")

    monkeypatch.setattr(youtube_import.requests, "Session", TooLongSession)
    with pytest.raises(YouTubeImportError, match="YOUTUBE_IMPORT_FAILED") as error:
        download_youtube_source(
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path,
            max_minutes=15,
            remaining_minutes=9,
            max_bytes=20 * 1024 * 1024,
            ingestion_provider="socialkit",
            socialkit_access_key="test-key",
            socialkit_poll_interval_seconds=0.01,
        )
    assert "9 Karo Minutes left" in error.value.public_message

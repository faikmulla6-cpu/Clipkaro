from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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

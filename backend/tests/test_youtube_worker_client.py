from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services.storage import ObjectMetadata
from app.services.youtube_import import YouTubeImportError
from app.services import youtube_worker_client


class FakeStorage:
    def __init__(self, *, size: int = 12345, content_type: str = "video/mp4") -> None:
        self.size = size
        self.content_type = content_type
        self.deleted: list[tuple[str, str | None]] = []
        self.signed: list[tuple[str, str, int]] = []

    async def signed_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str:
        self.signed.append((key, content_type, ttl_seconds))
        return "https://bucket.s3.us-west-004.backblazeb2.com/object?signature=test"

    async def stat(self, key: str) -> ObjectMetadata:
        return ObjectMetadata(key=key, size=self.size, content_type=self.content_type, generation="version:1")

    async def delete(self, key: str, *, generation: str | None = None) -> bool:
        self.deleted.append((key, generation))
        return True
class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def json(self) -> dict[str, object]:
        return self.payload


class FakeClient:
    calls: list[dict[str, object]] = []
    payload = {
        "video_id": "wgcfwWw7Mj4",
        "title": "Cosmos Laundromat",
        "duration": 720.0,
        "size": 12345,
        "content_type": "video/mp4",
    }

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, json: dict, headers: dict[str, str]):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(dict(self.payload))
def test_worker_ingestion_uses_presigned_upload_and_verifies_storage(monkeypatch) -> None:
    FakeClient.calls.clear()
    monkeypatch.setattr(youtube_worker_client.httpx, "AsyncClient", FakeClient)
    storage = FakeStorage()
    result = asyncio.run(youtube_worker_client.ingest_youtube_to_storage(
        "https://youtu.be/wgcfwWw7Mj4",
        user_id="user-1",
        project_id="project-1",
        max_minutes=15,
        remaining_minutes=15,
        max_bytes=500 * 1024 * 1024,
        storage=storage,
        worker_url="https://worker.example.com",
        worker_secret="A9-worker-secret-with-enough-diversity-2026!",
        timeout_seconds=900,
        upload_ttl_seconds=1200,
    ))
    assert result.video_id == "wgcfwWw7Mj4"
    assert result.metadata.size == 12345
    assert result.object_key.startswith("users/user-1/projects/project-1/source/")
    assert storage.signed and storage.signed[0][1] == "video/mp4"
    call = FakeClient.calls[0]
    assert call["url"] == "https://worker.example.com/v1/ingest/youtube"
    assert call["headers"]["Authorization"].startswith("Bearer ")
    assert call["json"]["expected_video_id"] == "wgcfwWw7Mj4"
    assert not storage.deleted
def test_worker_ingestion_rejects_unverified_size(monkeypatch) -> None:
    monkeypatch.setattr(youtube_worker_client.httpx, "AsyncClient", FakeClient)
    storage = FakeStorage(size=999)
    with pytest.raises(YouTubeImportError) as error:
        asyncio.run(youtube_worker_client.ingest_youtube_to_storage(
            "https://www.youtube.com/watch?v=wgcfwWw7Mj4",
            user_id="user-1",
            project_id="project-1",
            max_minutes=15,
            remaining_minutes=15,
            max_bytes=500 * 1024 * 1024,
            storage=storage,
            worker_url="https://worker.example.com",
            worker_secret="A9-worker-secret-with-enough-diversity-2026!",
            timeout_seconds=900,
            upload_ttl_seconds=1200,
        ))
    assert "Private storage could not verify" in error.value.public_message
    assert storage.deleted


def test_worker_ingestion_requires_strong_shared_secret() -> None:
    storage = FakeStorage()
    with pytest.raises(YouTubeImportError) as error:
        asyncio.run(youtube_worker_client.ingest_youtube_to_storage(
            "https://youtu.be/wgcfwWw7Mj4",
            user_id="user-1", project_id="project-1",
            max_minutes=15, remaining_minutes=15, max_bytes=500 * 1024 * 1024,
            storage=storage, worker_url="https://worker.example.com",
            worker_secret="short", timeout_seconds=900, upload_ttl_seconds=1200,
        ))
    assert "not configured" in error.value.public_message
    assert not storage.signed

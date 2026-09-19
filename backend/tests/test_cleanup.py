import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import cleanup


def test_cloud_retention_accepts_quarantine_and_isolates_invalid_video_key(monkeypatch):
    fetch = AsyncMock(side_effect=[
        [
            {"id": "bad", "file_path": "legacy/outside.mp4"},
            {"id": "quarantine", "file_path": "quarantine/u1/session/source.mp4"},
            {"id": "durable", "file_path": "users/u1/projects/p1/source/source.mp4"},
        ],
        [],
        [],
    ])
    execute = AsyncMock()
    storage = SimpleNamespace(delete=AsyncMock(return_value=True))
    monkeypatch.setattr(cleanup, "fetch_all", fetch)
    monkeypatch.setattr(cleanup, "execute", execute)
    monkeypatch.setattr(
        cleanup, "get_settings",
        lambda: SimpleNamespace(normalized_storage_backend="gcs"),
    )
    monkeypatch.setattr(cleanup, "get_storage_provider", lambda: storage)

    removed = asyncio.run(cleanup.cleanup_expired())

    assert removed == 2
    assert [call.args[0] for call in storage.delete.await_args_list] == [
        "quarantine/u1/session/source.mp4",
        "users/u1/projects/p1/source/source.mp4",
    ]
    updated_ids = [call.args[1][0] for call in execute.await_args_list if call.args[0].startswith("UPDATE videos")]
    assert updated_ids == ["quarantine", "durable"]


def test_cloud_retention_expires_abandoned_quarantine_upload_sessions(monkeypatch):
    fetch = AsyncMock(side_effect=[
        [],
        [],
        [
            {"id": "session-1", "object_key": "quarantine/u1/s1/a.mp4"},
            {"id": "session-2", "object_key": "quarantine/u1/s2/b.mp4"},
        ],
    ])
    execute = AsyncMock()
    storage = SimpleNamespace(delete=AsyncMock(return_value=True))
    monkeypatch.setattr(cleanup, "fetch_all", fetch)
    monkeypatch.setattr(cleanup, "execute", execute)
    monkeypatch.setattr(
        cleanup, "get_settings",
        lambda: SimpleNamespace(normalized_storage_backend="gcs"),
    )
    monkeypatch.setattr(cleanup, "get_storage_provider", lambda: storage)

    removed = asyncio.run(cleanup.cleanup_expired())

    assert removed == 2
    assert storage.delete.await_count == 2
    session_updates = [
        call for call in execute.await_args_list
        if call.args[0].startswith("UPDATE upload_sessions SET status='expired'")
    ]
    assert [call.args[1][0] for call in session_updates] == ["session-1", "session-2"]

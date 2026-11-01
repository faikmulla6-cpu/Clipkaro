import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError

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


def _provider_error():
    return ClientError(
        {"Error": {"Code": "ServiceUnavailable", "Message": "private provider details"},
         "ResponseMetadata": {"HTTPStatusCode": 503}},
        "DeleteObject",
    )


def test_r2_provider_error_does_not_skip_later_retention_items(monkeypatch, caplog):
    failed = {
        "users/u1/projects/p1/source/bad.mp4",
        "users/u1/projects/p1/exports/bad.mp4",
        "quarantine/u1/s1/bad.mp4",
    }
    keys = [
        "users/u1/projects/p1/source/bad.mp4",
        "users/u1/projects/p1/source/good.mp4",
        "users/u1/projects/p1/exports/bad.mp4",
        "users/u1/projects/p1/exports/good.mp4",
        "quarantine/u1/s1/bad.mp4",
        "quarantine/u1/s1/good.mp4",
    ]

    async def delete(key):
        if key in failed:
            raise _provider_error()
        return True

    storage = SimpleNamespace(delete=AsyncMock(side_effect=delete))
    fetch = AsyncMock(side_effect=[
        [{"id": "video-bad", "file_path": keys[0]},
         {"id": "video-good", "file_path": keys[1]}],
        [{"id": "export-bad", "output_path": keys[2]},
         {"id": "export-good", "output_path": keys[3]}],
        [{"id": "session-bad", "object_key": keys[4]},
         {"id": "session-good", "object_key": keys[5]}],
    ])
    execute = AsyncMock()
    monkeypatch.setattr(cleanup, "fetch_all", fetch)
    monkeypatch.setattr(cleanup, "execute", execute)
    monkeypatch.setattr(
        cleanup, "get_settings",
        lambda: SimpleNamespace(normalized_storage_backend="gcs"),
    )
    monkeypatch.setattr(cleanup, "get_storage_provider", lambda: storage)

    assert asyncio.run(cleanup.cleanup_expired()) == 3
    assert [call.args[0] for call in storage.delete.await_args_list] == keys
    assert [call.args[1][0] for call in execute.await_args_list] == [
        "video-good", "export-good", "session-good",
    ]
    assert "private provider details" not in caplog.text
    assert caplog.text.count("error_type=ClientError") == 3


def test_r2_failed_retention_item_remains_eligible_for_next_sweep(monkeypatch):
    key = "users/u1/projects/p1/source/retry.mp4"
    fetch = AsyncMock(side_effect=[
        [{"id": "retry-video", "file_path": key}], [], [],
        [{"id": "retry-video", "file_path": key}], [], [],
    ])
    storage = SimpleNamespace(delete=AsyncMock(side_effect=[
        _provider_error(), True,
    ]))
    execute = AsyncMock()
    monkeypatch.setattr(cleanup, "fetch_all", fetch)
    monkeypatch.setattr(cleanup, "execute", execute)
    monkeypatch.setattr(
        cleanup, "get_settings",
        lambda: SimpleNamespace(normalized_storage_backend="gcs"),
    )
    monkeypatch.setattr(cleanup, "get_storage_provider", lambda: storage)

    assert asyncio.run(cleanup.cleanup_expired()) == 0
    execute.assert_not_awaited()
    assert asyncio.run(cleanup.cleanup_expired()) == 1
    execute.assert_awaited_once_with(
        "UPDATE videos SET status='expired' WHERE id=?", ("retry-video",),
    )


def test_retention_does_not_swallow_database_failure_or_cancellation(monkeypatch):
    key = "users/u1/projects/p1/source/data.mp4"
    records = [{"id": "video-id", "file_path": key}]
    monkeypatch.setattr(cleanup, "fetch_all", AsyncMock(side_effect=[
        records, [], [], records, [], [],
    ]))
    monkeypatch.setattr(
        cleanup, "get_settings",
        lambda: SimpleNamespace(normalized_storage_backend="gcs"),
    )
    monkeypatch.setattr(cleanup, "execute", AsyncMock(side_effect=RuntimeError("database unavailable")))
    storage = SimpleNamespace(delete=AsyncMock(return_value=True))
    monkeypatch.setattr(cleanup, "get_storage_provider", lambda: storage)

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(cleanup.cleanup_expired())

    storage.delete = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cleanup.cleanup_expired())

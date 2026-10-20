"""Cleanup only abandoned and expired private upload sessions."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import upload_cleanup


@pytest.mark.asyncio
async def test_expired_multipart_is_aborted_and_private_key_cleaned(monkeypatch):
    s={"id":"s1","user_id":"u1","object_key":"quarantine/u1/s1/source.mp4",
       "object_generation":"multipart:provider-upload-id"}
    provider=SimpleNamespace(abort_multipart=AsyncMock(),delete=AsyncMock(return_value=False))
    monkeypatch.setattr(upload_cleanup,"cloud_object_storage_enabled",lambda:True)
    monkeypatch.setattr(upload_cleanup,"get_storage_provider",lambda:provider)
    get_rows=AsyncMock(return_value=[s])
    write=AsyncMock()
    monkeypatch.setattr(upload_cleanup,"fetch_all",get_rows)
    monkeypatch.setattr(upload_cleanup,"execute",write)
    class Claimed:
        async def fetchone(self):
            return {"id": "s1"}
    class Transaction:
        async def execute(self, sql, values):
            assert "status='expired'" in sql and "RETURNING id" in sql
            return Claimed()
    async def claim(callback, **kwargs):
        return await callback(Transaction())
    monkeypatch.setattr(upload_cleanup,"run_in_transaction",claim)
    result=await upload_cleanup.sweep_expired_uploads(now=datetime(2026,10,20,12,0,tzinfo=timezone.utc))
    assert result==1
    sql,values=get_rows.await_args.args
    assert "status='initiated'" in sql and "expires_at<" in sql
    assert values[1]==100
    provider.abort_multipart.assert_awaited_once_with("quarantine/u1/s1/source.mp4","provider-upload-id")
    provider.delete.assert_awaited_once_with("quarantine/u1/s1/source.mp4")
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_never_mutates_keys_outside_creator_prefix(monkeypatch):
    session={"id":"s2","user_id":"u1","object_key":"quarantine/u2/s2/other-user.mp4",
             "object_generation":"multipart:provider-id"}
    storage=SimpleNamespace(abort_multipart=AsyncMock(),delete=AsyncMock())
    write=AsyncMock()
    monkeypatch.setattr(upload_cleanup,"cloud_object_storage_enabled",lambda:True)
    monkeypatch.setattr(upload_cleanup,"get_storage_provider",lambda:storage)
    monkeypatch.setattr(upload_cleanup,"fetch_all",AsyncMock(return_value=[session]))
    monkeypatch.setattr(upload_cleanup,"execute",write)
    class Claimed:
        async def fetchone(self):
            return {"id": "s2"}
    class Transaction:
        async def execute(self, sql, values):
            return Claimed()
    async def claim(callback, **kwargs):
        return await callback(Transaction())
    monkeypatch.setattr(upload_cleanup,"run_in_transaction",claim)
    assert await upload_cleanup.sweep_expired_uploads()==0
    storage.abort_multipart.assert_not_awaited()
    storage.delete.assert_not_awaited()
    write.assert_awaited_once()
    assert "status='initiated'" in write.await_args.args[0]


@pytest.mark.asyncio
async def test_cleanup_skips_local_storage(monkeypatch):
    monkeypatch.setattr(upload_cleanup,"cloud_object_storage_enabled",lambda:False)
    fetch=AsyncMock()
    monkeypatch.setattr(upload_cleanup,"fetch_all",fetch)
    assert await upload_cleanup.sweep_expired_uploads()==0
    fetch.assert_not_awaited()

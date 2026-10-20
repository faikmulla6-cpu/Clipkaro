"""Secure bounded S3 multipart upload contracts (no external storage calls)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import cloud_uploads
from app.api.cloud_uploads import UploadInitRequest
from app.services.storage import ObjectMetadata, S3StorageProvider
from app.services.upload_limits import MB, PART_BYTES, UPLOAD_LIMIT_MB, allowed_upload_mb


@pytest.mark.parametrize("plan,maximum", [
    ("free",500),("mini_pass",500),("creator",1024),
    ("growth",2048),("pro",4096),("agency",4096),
])
def test_upload_plan_limits_and_local_safety(plan, maximum, monkeypatch):
    monkeypatch.setattr(
        "app.services.upload_limits.get_settings",
        lambda: SimpleNamespace(max_upload_mb=4096),
    )
    assert allowed_upload_mb(plan, cloud_multipart=True) == maximum
    assert allowed_upload_mb(plan, cloud_multipart=False) == 500
    assert PART_BYTES == 64 * MB


@pytest.mark.asyncio
async def test_pro_upload_uses_private_signed_parts_and_stores_upload_id(monkeypatch):
    provider=SimpleNamespace(
        start_multipart=AsyncMock(return_value="server-assigned-upload-id"),
        signed_part_url=AsyncMock(side_effect=lambda key, uid, part, **kw: f"https://safe.invalid/part/{part}"),
        abort_multipart=AsyncMock(),
    )
    rows=[]
    async def insert(sql, values):
        rows.append((sql, values))
    settings=SimpleNamespace(max_upload_mb=4096,multipart_upload_ttl_seconds=10800,
                             gcs_upload_url_ttl_seconds=900)
    monkeypatch.setattr(cloud_uploads,"get_settings",lambda:settings)
    monkeypatch.setattr(cloud_uploads,"get_storage_provider",lambda:provider)
    monkeypatch.setattr(cloud_uploads,"object_storage_provider_name",lambda:"s3")
    monkeypatch.setattr(cloud_uploads,"cloud_object_storage_enabled",lambda:True)
    monkeypatch.setattr(cloud_uploads.project_routes,"get_usage_for",
        AsyncMock(return_value=SimpleNamespace(
            plan="pro",shorts_remaining=80,processing_minutes_remaining=400)))
    monkeypatch.setattr(cloud_uploads,"fetch_one",AsyncMock(return_value={"total":0}))
    monkeypatch.setattr(cloud_uploads,"execute",insert)
    size=3*1024*MB
    req=UploadInitRequest(filename="podcast.mp4",content_type="video/mp4",size=size)
    response=await cloud_uploads.initialize_upload(req,user={"id":"creator-1"})
    assert response["method"]=="MULTIPART"
    assert response["part_size"]==PART_BYTES
    assert len(response["parts"]) == 48
    assert response["parts"][0]["part_number"] == 1
    assert response["parts"][-1]["part_number"] == 48
    assert all(p["upload_url"].startswith("https://") for p in response["parts"])
    assert "upload_id" not in response
    assert len(rows) == 1
    query,params=rows[0]
    assert "upload_sessions" in query
    assert "multipart:server-assigned-upload-id" in params
    assert "quarantine/creator-1/" in str(params)
    provider.abort_multipart.assert_not_awaited()
    provider.signed_part_url.assert_awaited()


@pytest.mark.asyncio
async def test_mini_pass_oversize_is_rejected_before_touching_storage(monkeypatch):
    provider=SimpleNamespace(start_multipart=AsyncMock())
    monkeypatch.setattr(cloud_uploads,"get_settings",
        lambda: SimpleNamespace(max_upload_mb=4096))
    monkeypatch.setattr(cloud_uploads,"cloud_object_storage_enabled",lambda:True)
    monkeypatch.setattr(cloud_uploads,"object_storage_provider_name",lambda:"s3")
    monkeypatch.setattr(cloud_uploads.project_routes,"get_usage_for",
        AsyncMock(return_value=SimpleNamespace(
            plan="mini_pass",shorts_remaining=5,processing_minutes_remaining=25)))
    monkeypatch.setattr(cloud_uploads,"get_storage_provider",lambda:provider)
    req=UploadInitRequest(filename="source.mp4",content_type="video/mp4",size=501*MB)
    with pytest.raises(HTTPException) as exc:
        await cloud_uploads.initialize_upload(req,user={"id":"creator-1"})
    assert exc.value.status_code==413
    provider.start_multipart.assert_not_awaited()


class FakeS3:
    def __init__(self, sizes):
        self.sizes=sizes
        self.completed=[]
        self.aborted=[]
    def list_parts(self, **kwargs):
        return {"IsTruncated":False,"Parts":[
            {"PartNumber":i+1,"Size":size,"ETag":f'"part-{i+1}"'}
            for i,size in enumerate(self.sizes)
        ]}
    def complete_multipart_upload(self, **kwargs):
        self.completed.append(kwargs)
    def abort_multipart_upload(self, **kwargs):
        self.aborted.append(kwargs)


@pytest.mark.asyncio
async def test_finalize_validates_every_size_before_object_creation(monkeypatch):
    fake=FakeS3([PART_BYTES,PART_BYTES // 2])
    provider=object.__new__(S3StorageProvider)
    provider.bucket="private"
    provider.client=fake
    provider.stat=AsyncMock(return_value=ObjectMetadata(
        "quarantine/u/s/video.mp4", PART_BYTES+10,
        "video/mp4", "etag:abc",
    ))
    with pytest.raises(ValueError,match="missing or incomplete"):
        await provider.finish_multipart("quarantine/u/s/video.mp4","u123",
                                        expected_size=PART_BYTES+10,part_size=PART_BYTES)
    assert not fake.completed
    fake.sizes=[PART_BYTES,10]
    result=await provider.finish_multipart("quarantine/u/s/video.mp4","u123",
                                           expected_size=PART_BYTES+10,part_size=PART_BYTES)
    assert result.size==PART_BYTES+10
    assert fake.completed[0]["MultipartUpload"]["Parts"][1]["ETag"] == '"part-2"'


@pytest.mark.asyncio
async def test_finalize_rejects_missing_parts(monkeypatch):
    fake=FakeS3([PART_BYTES])
    provider=object.__new__(S3StorageProvider)
    provider.bucket="private"
    provider.client=fake
    with pytest.raises(ValueError,match="incomplete"):
        await provider.finish_multipart("quarantine/u/s/video.mp4","upload-id",
                                        expected_size=PART_BYTES+100,part_size=PART_BYTES)
    assert not fake.completed


@pytest.mark.asyncio
async def test_abort_requires_account_ownership_and_preconsumption(monkeypatch):
    provider=SimpleNamespace(abort_multipart=AsyncMock(),delete=AsyncMock())
    monkeypatch.setattr(cloud_uploads,"get_storage_provider",lambda:provider)
    monkeypatch.setattr(cloud_uploads,"execute",AsyncMock())
    class Claimed:
        async def fetchone(self):
            return {"id": "session-1"}
    class Transaction:
        async def execute(self, query, values):
            assert "RETURNING id" in query and "status='rejected'" in query
            return Claimed()
    async def claim(callback, **kwargs):
        return await callback(Transaction())
    monkeypatch.setattr(cloud_uploads,"run_in_transaction",claim)
    monkeypatch.setattr(cloud_uploads,"fetch_one",AsyncMock(return_value={
        "status":"initiated","object_key":"quarantine/u1/s/clip.mp4",
        "object_generation":"multipart:srv-upload-id",
    }))
    result=await cloud_uploads.abort_upload("session-1",user={"id":"u1"})
    assert result=={"status":"aborted"}
    provider.abort_multipart.assert_awaited_once_with(
        "quarantine/u1/s/clip.mp4","srv-upload-id",
    )
    provider.delete.assert_awaited_once_with("quarantine/u1/s/clip.mp4")
    cloud_uploads.execute.assert_not_awaited()
    cloud_uploads.fetch_one.assert_awaited_once()
    assert cloud_uploads.fetch_one.await_args.args[1]==("session-1","u1")


@pytest.mark.asyncio
async def test_completed_session_cannot_abort(monkeypatch):
    monkeypatch.setattr(cloud_uploads,"fetch_one",
        AsyncMock(return_value={"status":"consumed","object_generation":"multipart:u1"}))
    with pytest.raises(HTTPException) as exc:
        await cloud_uploads.abort_upload("session-1",user={"id":"u1"})
    assert exc.value.status_code==409

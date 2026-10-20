"""Authenticated multipart lifecycle using real SQLite transactions, no cloud writes."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import cloud_uploads
from app.core.config import get_settings
from app.core.database import fetch_one
from app.main import app
from app.services.legal import LEGAL_VERSION
from app.services.storage import ObjectMetadata
from app.services.upload_limits import MB


@pytest.fixture()
def client(tmp_path, monkeypatch):
    settings = get_settings()
    original={name:getattr(settings,name) for name in
             ("app_env","database_path","storage_root","secret_key","seed_demo_user",
              "database_backend","allow_manual_analysis_in_development")}
    settings.app_env="test"
    settings.database_path=tmp_path/"multipart.db"
    settings.storage_root=tmp_path/"storage"
    settings.database_backend="sqlite"
    settings.secret_key="multipart-qa-signing-secret"
    settings.seed_demo_user=True
    settings.allow_manual_analysis_in_development=True
    provider=SimpleNamespace(
        start_multipart=AsyncMock(return_value="private-upload-id"),
        signed_part_url=AsyncMock(side_effect=lambda key,uid,n,**kw:f"https://signed.invalid/{n}"),
        stat=AsyncMock(return_value=None),
        finish_multipart=AsyncMock(),
        abort_multipart=AsyncMock(),
        delete=AsyncMock(return_value=False),
    )
    monkeypatch.setattr(cloud_uploads,"get_storage_provider",lambda:provider)
    monkeypatch.setattr(cloud_uploads,"object_storage_provider_name",lambda:"s3")
    monkeypatch.setattr(cloud_uploads,"cloud_object_storage_enabled",lambda:True)
    launcher=SimpleNamespace(launch=AsyncMock())
    monkeypatch.setattr(cloud_uploads,"get_job_launcher",lambda:launcher)
    try:
        with TestClient(app) as c:
            logged=c.post("/api/v1/auth/login",json={
                "email":"demo@clipkaro.ai","password":"ClipKaro123!"})
            assert logged.status_code==200
            c.headers["X-CSRF-Token"]=c.cookies.get("csrf_token")
            accepted=c.post("/api/v1/legal/accept",json={
                "accepted":True,"version":LEGAL_VERSION})
            assert accepted.status_code==200
            yield c,provider,launcher
    finally:
        for name,value in original.items():
            setattr(settings,name,value)


def test_authenticated_multipart_init_completion_idempotence(client):
    c,provider,launcher=client
    size=144*MB
    response=c.post("/api/v1/uploads/init",json={
        "filename":"meeting.mp4","size":size,"content_type":"video/mp4",
        "title":"Meeting","language":"hi","category":"podcast",
    })
    assert response.status_code==200,response.text
    init=response.json()
    assert init["method"]=="MULTIPART"
    assert len(init["parts"])==3
    session_id=init["upload_session_id"]
    key=asyncio.run(fetch_one("SELECT object_key,object_generation,status FROM upload_sessions WHERE id=?",(session_id,)))
    assert key["status"]=="initiated"
    assert key["object_generation"]=="multipart:private-upload-id"
    assert key["object_key"].startswith("quarantine/")
    provider.finish_multipart.return_value=ObjectMetadata(
        key=key["object_key"],size=size,content_type="video/mp4",
        generation="etag:complete",
    )
    complete=c.post(f"/api/v1/uploads/{session_id}/complete")
    assert complete.status_code==200,complete.text
    assert complete.json()["status"]=="queued"
    provider.finish_multipart.assert_awaited_once()
    launcher.launch.assert_awaited_once()
    stored=asyncio.run(fetch_one("SELECT object_generation FROM videos WHERE id=(SELECT json_extract(payload_json,'$.video_id') FROM job_payloads WHERE job_id=?)",(complete.json()["job_id"],)))
    assert stored["object_generation"]=="etag:complete"
    repeat=c.post(f"/api/v1/uploads/{session_id}/complete")
    assert repeat.status_code==200
    assert repeat.json()["project_id"]==complete.json()["project_id"]
    provider.finish_multipart.assert_awaited_once()
    cannot_abort=c.post(f"/api/v1/uploads/{session_id}/abort")
    assert cannot_abort.status_code==409


def test_abort_session_never_creates_project(client):
    c,provider,launcher=client
    session=c.post("/api/v1/uploads/init",json={
        "filename":"podcast.mp4","size":128*MB,"content_type":"video/mp4"}).json()
    sid=session["upload_session_id"]
    cancelled=c.post(f"/api/v1/uploads/{sid}/abort")
    assert cancelled.status_code==200
    provider.abort_multipart.assert_awaited()
    row=asyncio.run(fetch_one("SELECT status,project_id FROM upload_sessions WHERE id=?",(sid,)))
    # Client receives "aborted"; PostgreSQL-compatible persisted status is "rejected".
    assert row["status"]=="rejected"
    assert row["project_id"] is None
    assert c.post(f"/api/v1/uploads/{sid}/complete").status_code==410
    launcher.launch.assert_not_awaited()

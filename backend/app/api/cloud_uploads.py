from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import execute, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.hinglish_stage1_routing import resolve_stage1_route
from app.services.job_launcher import JobLaunchError, get_job_launcher
from app.services.storage import get_storage_provider
from app.services.video import upload_type_supported

router = APIRouter()
_ALLOWED_MIME = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/matroska", "application/octet-stream"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size: int = Field(gt=0)
    title: str = Field(default="Untitled video", max_length=120)
    language: str = Field(default="auto", max_length=32)
    category: str = Field(default="auto", max_length=64)


async def init_cloud_uploads() -> None:
    if get_settings().normalized_database_backend != "sqlite":
        return
    await execute(
        """CREATE TABLE IF NOT EXISTS upload_sessions (
          id TEXT PRIMARY KEY,user_id TEXT NOT NULL,object_key TEXT UNIQUE NOT NULL,original_filename TEXT NOT NULL,
          expected_size INTEGER NOT NULL,expected_content_type TEXT NOT NULL,object_generation TEXT,status TEXT NOT NULL,
          title TEXT NOT NULL,language TEXT NOT NULL,category TEXT NOT NULL,project_id TEXT,job_id TEXT,
          expires_at TEXT NOT NULL,created_at TEXT NOT NULL,consumed_at TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)"""
    )


@router.post("/uploads/init", status_code=201)
async def initialize_upload(body: UploadInitRequest, user: dict = Depends(current_user)) -> dict[str, Any]:
    settings = get_settings()
    if settings.normalized_storage_backend != "gcs":
        raise HTTPException(409, "Direct cloud upload is enabled only in GCS mode.")
    filename = Path(body.filename).name
    content_type = body.content_type.strip().lower()
    if not upload_type_supported(filename, content_type) or content_type not in _ALLOWED_MIME:
        raise HTTPException(415, "Only MP4, MOV, WebM, and MKV videos are supported.")
    if body.size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Video exceeds the {settings.max_upload_mb} MB plan limit.")
    session_id = str(uuid.uuid4())
    suffix = Path(filename).suffix.lower()
    object_key = f"quarantine/{user['id']}/{session_id}/{uuid.uuid4().hex}{suffix}"
    created = _now()
    upload_ttl = min(900, max(60, settings.gcs_upload_url_ttl_seconds))
    expires = created + timedelta(seconds=upload_ttl)
    await execute(
        """INSERT INTO upload_sessions(id,user_id,object_key,original_filename,expected_size,expected_content_type,
           object_generation,status,title,language,category,project_id,job_id,expires_at,created_at,consumed_at)
           VALUES (?,?,?,?,?,?,'','initiated',?,?,?,?,?,?,?,NULL)""",
        (session_id, user["id"], object_key, filename, body.size, content_type, body.title[:120], body.language, body.category, None, None, expires.isoformat(), created.isoformat()),
    )
    signed_url = await get_storage_provider().signed_upload_url(
        object_key, content_type=content_type, ttl_seconds=upload_ttl
    )
    return {"upload_session_id": session_id, "method": "PUT", "upload_url": signed_url, "headers": {"Content-Type": content_type}, "expires_at": expires.isoformat()}


@router.post("/uploads/{session_id}/complete", status_code=202)
async def complete_upload(session_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    session = await fetch_one("SELECT * FROM upload_sessions WHERE id=? AND user_id=?", (session_id, user["id"]))
    if not session:
        raise HTTPException(404, "Upload session not found.")
    if session.get("status") == "consumed":
        job = await fetch_one("SELECT status,stage FROM jobs WHERE id=? AND user_id=?", (session["job_id"], user["id"]))
        if job and job.get("stage") == "launch_failed":
            await execute("UPDATE jobs SET status='queued',stage='queued',error=NULL,updated_at=? WHERE id=?", (_now().isoformat(), session["job_id"]))
            try:
                await get_job_launcher().launch(str(session["job_id"]))
            except JobLaunchError as exc:
                raise HTTPException(503, "Processing could not restart yet. Retry shortly.") from exc
        return {"project_id": session["project_id"], "job_id": session["job_id"], "status": (job or {}).get("status", "queued")}
    if session.get("status") != "initiated" or datetime.fromisoformat(session["expires_at"]) <= _now():
        raise HTTPException(410, "Upload session expired or is no longer usable.")
    metadata = await get_storage_provider().stat(session["object_key"])
    if not metadata:
        raise HTTPException(409, "The uploaded object is not available yet.")
    if metadata.size != int(session["expected_size"]):
        await execute("UPDATE upload_sessions SET status='rejected' WHERE id=?", (session_id,))
        raise HTTPException(422, "Uploaded object size did not match the authorized upload.")
    if metadata.content_type.lower() != str(session["expected_content_type"]).lower():
        await execute("UPDATE upload_sessions SET status='rejected' WHERE id=?", (session_id,))
        raise HTTPException(422, "Uploaded object content type did not match the authorized upload.")
    project_id, video_id, job_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    timestamp = _now().isoformat()
    expires = (_now() + timedelta(hours=get_settings().file_expiry_hours)).isoformat()
    route = resolve_stage1_route(str(session["language"]), str(user["id"]))
    payload = json.dumps({"video_id": video_id, **route}, separators=(",", ":"))

    async def persist(db) -> None:
        lock = " FOR UPDATE" if get_settings().normalized_database_backend == "postgres" else ""
        cursor = await db.execute("SELECT status FROM upload_sessions WHERE id=? AND user_id=?" + lock, (session_id, user["id"]))
        locked = await cursor.fetchone()
        if not locked or locked["status"] != "initiated":
            raise RuntimeError("Upload session was already consumed.")
        await db.execute("INSERT INTO projects VALUES (?, ?, ?, '', 'queued', 0, 'queued', ?, ?, NULL, ?, ?)", (project_id, user["id"], session["title"], session["language"], session["category"], timestamp, timestamp))
        await db.execute("INSERT INTO videos(id,project_id,original_filename,duration,width,height,file_size,file_path,object_generation,status,created_at,expires_at) VALUES (?,?,?,0,0,0,?,?,?,'uploaded',?,?)", (video_id, project_id, session["original_filename"], metadata.size, session["object_key"], metadata.generation, timestamp, expires))
        await db.execute("INSERT INTO jobs(id,user_id,project_id,export_id,kind,status,progress,stage,message,error,created_at,updated_at) VALUES (?,?,?,NULL,'process_video','queued',0,'queued','Waiting to start',NULL,?,?)", (job_id, user["id"], project_id, timestamp, timestamp))
        await db.execute("INSERT INTO job_payloads(job_id,payload_json,created_at,updated_at) VALUES (?,?,?,?)", (job_id, payload, timestamp, timestamp))
        await db.execute("UPDATE upload_sessions SET status='consumed',object_generation=?,project_id=?,job_id=?,consumed_at=? WHERE id=? AND status='initiated'", (metadata.generation, project_id, job_id, timestamp, session_id))

    try:
        await run_in_transaction(persist, operation_name="complete direct upload")
        await get_job_launcher().launch(job_id)
    except JobLaunchError as exc:
        await execute("UPDATE jobs SET status='failed',stage='launch_failed',error='Media job launch failed',failed_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, job_id))
        raise HTTPException(503, "Video was stored safely, but processing could not start. Retry shortly.") from exc
    return {"project_id": project_id, "job_id": job_id, "status": "queued"}

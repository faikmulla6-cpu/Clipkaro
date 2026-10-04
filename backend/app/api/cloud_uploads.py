from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import distributed_advisory_lock, execute, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.email_verification import requires_verification_for_processing
from app.services.hinglish_stage1_routing import resolve_stage1_route
from app.services.job_launcher import JobLaunchError, get_job_launcher
from app.services.storage import cloud_object_storage_enabled, get_storage_provider
from app.services.video import upload_type_supported
from app.services.youtube_import import canonicalize_youtube_url

router = APIRouter()
logger = logging.getLogger("clipkaro.cloud_uploads")
_ALLOWED_MIME = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/matroska", "application/octet-stream"}
_ALLOWED_LANGUAGES = {"auto", "en", "hi", "hinglish", "mr"}
_ALLOWED_CATEGORIES = {"auto", "education", "podcast", "business", "motivation", "spiritual", "local-business"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size: int = Field(gt=0)
    title: str = Field(default="Untitled video", max_length=120)
    language: str = Field(default="auto", max_length=32)
    category: str = Field(default="auto", max_length=64)


class YouTubeImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    title: str = Field(default="", max_length=120)
    language: str = Field(default="auto", max_length=32)
    category: str = Field(default="auto", max_length=64)
    rights_confirmed: bool = False


async def _reject_if_youtube_import_active(db, user_id: str) -> None:
    cursor = await db.execute(
        """SELECT id FROM jobs WHERE user_id=? AND kind='import_youtube'
           AND status IN ('queued','processing') LIMIT 1""",
        (user_id,),
    )
    if await cursor.fetchone():
        raise HTTPException(
            409,
            "One YouTube video is already processing. Wait for it to finish before starting another.",
        )


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


@router.post("/uploads/init")
async def initialize_upload(body: UploadInitRequest, user: dict = Depends(current_user)) -> dict[str, Any]:
    settings = get_settings()
    if not cloud_object_storage_enabled():
        raise HTTPException(409, "Direct cloud upload is not enabled for this environment.")
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


@router.post("/uploads/{session_id}/complete")
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
    try:
        metadata = await get_storage_provider().stat(session["object_key"])
    except Exception:
        logger.exception(
            "uploaded_object_verification_failed upload_session_id=%s",
            session_id,
        )
        raise HTTPException(
            503,
            "Private media storage could not verify the uploaded video. Please retry shortly.",
        ) from None
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


@router.post("/imports/youtube", status_code=202)
async def import_youtube(body: YouTubeImportRequest, user: dict = Depends(current_user)) -> dict[str, Any]:
    """Queue one creator-authorized YouTube video for the existing media pipeline."""
    if requires_verification_for_processing(user):
        raise HTTPException(
            403,
            {"message": "Verify your email before starting AI processing.", "code": "EMAIL_VERIFICATION_REQUIRED"},
        )
    if not cloud_object_storage_enabled():
        raise HTTPException(409, "YouTube importing requires private cloud media storage.")
    if not body.rights_confirmed:
        raise HTTPException(422, "Confirm that you own this video or have permission to create clips from it.")
    if body.language not in _ALLOWED_LANGUAGES or body.category not in _ALLOWED_CATEGORIES:
        raise HTTPException(422, "Choose a supported language and content type.")
    try:
        canonical_url, youtube_video_id = canonicalize_youtube_url(body.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    project_id, video_id, job_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    timestamp = _now().isoformat()
    expires = (_now() + timedelta(hours=get_settings().file_expiry_hours)).isoformat()
    custom_title = body.title.strip()
    title = custom_title or "YouTube video"
    # The placeholder is already inside the project's authorized private prefix.
    # The worker replaces the extension/generation only after malware scanning.
    source_key = f"users/{user['id']}/projects/{project_id}/source/source.mp4"
    route = resolve_stage1_route(body.language, str(user["id"]))
    payload = json.dumps(
        {
            "video_id": video_id,
            "canonical_url": canonical_url,
            "youtube_video_id": youtube_video_id,
            "title_is_custom": bool(custom_title),
            **route,
        },
        separators=(",", ":"),
    )

    async def persist(db) -> None:
        await _reject_if_youtube_import_active(db, str(user["id"]))
        await db.execute(
            "INSERT INTO projects VALUES (?, ?, ?, '', 'queued', 0, 'queued', ?, ?, NULL, ?, ?)",
            (project_id, user["id"], title[:120], body.language, body.category, timestamp, timestamp),
        )
        await db.execute(
            """INSERT INTO videos(id,project_id,original_filename,duration,width,height,file_size,file_path,
               object_generation,status,created_at,expires_at) VALUES (?,?,?,0,0,0,?,?,?,'uploaded',?,?)""",
            (video_id, project_id, f"youtube-{youtube_video_id}.mp4", 0, source_key, "", timestamp, expires),
        )
        await db.execute(
            """INSERT INTO jobs(id,user_id,project_id,export_id,kind,status,progress,stage,message,error,created_at,updated_at)
               VALUES (?,?,?,NULL,'import_youtube','queued',0,'queued','Waiting to import YouTube video',NULL,?,?)""",
            (job_id, user["id"], project_id, timestamp, timestamp),
        )
        await db.execute(
            "INSERT INTO job_payloads(job_id,payload_json,created_at,updated_at) VALUES (?,?,?,?)",
            (job_id, payload, timestamp, timestamp),
        )

    # Keep one remote import active per creator. This matches the UI promise and
    # prevents accidental double-clicks/tabs from multiplying remote download cost.
    async with distributed_advisory_lock(f"clipkaro:youtube-import:{user['id']}"):
        await run_in_transaction(persist, operation_name="queue YouTube import")
    try:
        await get_job_launcher().launch(job_id)
    except JobLaunchError as exc:
        await execute(
            "UPDATE jobs SET status='failed',stage='launch_failed',message='Processing could not start',error='Media job launch failed',failed_at=?,updated_at=? WHERE id=?",
            (timestamp, timestamp, job_id),
        )
        await execute(
            "UPDATE projects SET status='failed',stage='failed',error='Processing could not start',updated_at=? WHERE id=?",
            (timestamp, project_id),
        )
        raise HTTPException(503, "Your project was saved, but processing could not start. Retry shortly.") from exc

    return {"project_id": project_id, "job_id": job_id, "status": "queued", "youtube_video_id": youtube_video_id}

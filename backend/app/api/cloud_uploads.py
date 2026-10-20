from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api import routes as project_routes
from app.core.config import get_settings
from app.core.database import distributed_advisory_lock, execute, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.email_verification import requires_verification_for_processing
from app.services.hinglish_stage1_routing import resolve_stage1_route
from app.services.job_launcher import JobLaunchError, get_job_launcher
from app.services.media_retention import source_media_expiry
from app.services.storage import cloud_object_storage_enabled, get_storage_provider, object_storage_provider_name
from app.services.upload_limits import MB, PART_BYTES, MULTIPART_THRESHOLD, allowed_upload_mb
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
    limits = await project_routes.get_usage_for(user)
    if limits.shorts_remaining <= 0:
        raise HTTPException(
            402,
            "No AI Short creation credits remain in this plan. Existing Shorts can still be edited, exported and re-exported.",
        )
    if limits.processing_minutes_remaining < 0.01:
        raise HTTPException(402, "No Karo Minutes remain for processing a new source video. Existing Shorts can still be re-exported.")
    if not cloud_object_storage_enabled():
        raise HTTPException(409, "Direct cloud upload is not enabled for this environment.")
    filename = Path(body.filename).name
    content_type = body.content_type.strip().lower()
    if not upload_type_supported(filename, content_type) or content_type not in _ALLOWED_MIME:
        raise HTTPException(415, "Only MP4, MOV, WebM, and MKV videos are supported.")
    supports_multipart = object_storage_provider_name() == "s3"
    maximum = allowed_upload_mb(limits.plan, cloud_multipart=supports_multipart)
    if body.size > maximum * MB:
        raise HTTPException(413, f"Video exceeds the {maximum} MB upload limit for this plan.")
    active = await fetch_one(
        "SELECT COUNT(*) AS total FROM upload_sessions WHERE user_id=? AND status='initiated' AND expires_at>?",
        (user["id"], _now().isoformat()),
    )
    if active and int(active["total"]) >= 3:
        raise HTTPException(429, "Three uploads are already open. Complete or cancel an existing upload first.")
    session_id = str(uuid.uuid4())
    suffix = Path(filename).suffix.lower()
    object_key = f"quarantine/{user['id']}/{session_id}/{uuid.uuid4().hex}{suffix}"
    created = _now()
    multipart = supports_multipart and body.size > MULTIPART_THRESHOLD
    upload_ttl = (
        min(10800, max(3600, int(settings.multipart_upload_ttl_seconds)))
        if multipart else min(3600, max(60, settings.gcs_upload_url_ttl_seconds))
    )
    expires = created + timedelta(seconds=upload_ttl)
    provider = get_storage_provider()
    upload_id = ""
    parts: list[dict[str, Any]] = []
    signed_url = ""
    try:
        if multipart:
            upload_id = await provider.start_multipart(object_key, content_type=content_type)
            count = (body.size + PART_BYTES - 1) // PART_BYTES
            if count > 10000:
                raise HTTPException(413, "Too many upload chunks.")
            for number in range(1, count + 1):
                signed_part = await provider.signed_part_url(
                    object_key, upload_id, number, ttl_seconds=upload_ttl,
                )
                parts.append({"part_number": number, "upload_url": signed_part})
        else:
            signed_url = await provider.signed_upload_url(
                object_key, content_type=content_type, ttl_seconds=upload_ttl,
            )
        await execute(
            """INSERT INTO upload_sessions(id,user_id,object_key,original_filename,expected_size,expected_content_type,
               object_generation,status,title,language,category,project_id,job_id,expires_at,created_at,consumed_at)
               VALUES (?,?,?,?,?,?,?,'initiated',?,?,?,?,?,?,?,NULL)""",
            (session_id, user["id"], object_key, filename, body.size, content_type,
             "multipart:" + upload_id if multipart else "", body.title[:120],
             body.language, body.category, None, None, expires.isoformat(), created.isoformat()),
        )
    except Exception:
        if upload_id:
            try:
                await provider.abort_multipart(object_key, upload_id)
            except Exception:
                logger.exception("multipart_initialization_cleanup_failed session=%s", session_id)
        raise
    if multipart:
        return {
            "upload_session_id": session_id, "method": "MULTIPART",
            "part_size": PART_BYTES, "parts": parts, "expires_at": expires.isoformat(),
        }
    return {
        "upload_session_id": session_id, "method": "PUT",
        "upload_url": signed_url, "headers": {"Content-Type": content_type},
        "expires_at": expires.isoformat(),
    }



@router.post("/uploads/{session_id}/abort")
async def abort_upload(session_id: str, user: dict = Depends(current_user)) -> dict[str, str]:
    session = await fetch_one(
        "SELECT * FROM upload_sessions WHERE id=? AND user_id=?",
        (session_id, user["id"]),
    )
    if not session:
        raise HTTPException(404, "Upload session not found.")
    if session["status"] == "rejected":
        return {"status": "aborted"}
    if session["status"] != "initiated":
        raise HTTPException(409, "This upload cannot be cancelled after completion.")

    # PostgreSQL already permits 'rejected'; don't invent a new status. Atomic
    # UPDATE ... RETURNING prevents a late cancellation from deleting a media
    # object whose upload session was consumed in parallel.
    async def claim(db) -> bool:
        cur = await db.execute(
            """UPDATE upload_sessions SET status='rejected'
               WHERE id=? AND user_id=? AND status='initiated' RETURNING id""",
            (session_id, user["id"]),
        )
        return await cur.fetchone() is not None

    if not await run_in_transaction(claim, operation_name="claim upload cancellation"):
        latest = await fetch_one(
            "SELECT status FROM upload_sessions WHERE id=? AND user_id=?",
            (session_id, user["id"]),
        )
        if latest and latest.get("status") == "rejected":
            return {"status": "aborted"}
        raise HTTPException(409, "This upload has already completed or changed state.")
    provider = get_storage_provider()
    try:
        upload_marker = str(session.get("object_generation") or "")
        if upload_marker.startswith("multipart:"):
            try:
                await provider.abort_multipart(
                    session["object_key"], upload_marker[len("multipart:"):],
                )
            except Exception as exc:
                code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
                if code not in {"NoSuchUpload", "404", "NotFound"}:
                    raise
        # Small signed single-PUT transfers may have already reached storage.
        # The random per-session quarantine key is safe to delete on cancel.
        await provider.delete(session["object_key"])
    except Exception:
        logger.exception("upload_cancellation_cleanup_failed session=%s", session_id)
        await execute(
            "UPDATE upload_sessions SET status='initiated' WHERE id=? AND user_id=? AND status='rejected'",
            (session_id, user["id"]),
        )
        raise HTTPException(503, "Storage could not cancel the upload yet. Retry shortly.") from None
    return {"status": "aborted"}



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
    # The existing PostgreSQL CHECK allows "uploaded" as a temporary
    # completion lease. Claim the session before ANY S3 operations so a
    # concurrent cancel/sweeper cannot destroy a source being finalized.
    async def claim_completion(db) -> bool:
        cur = await db.execute(
            """UPDATE upload_sessions SET status='uploaded'
               WHERE id=? AND user_id=? AND status='initiated'
               AND expires_at>? RETURNING id""",
            (session_id, user["id"], _now().isoformat()),
        )
        return await cur.fetchone() is not None

    if not await run_in_transaction(
        claim_completion, operation_name="claim direct upload completion",
    ):
        raise HTTPException(409, "This upload is being completed or cancelled. Try again shortly.")
    try:
        provider = get_storage_provider()
        upload_marker = str(session.get("object_generation") or "")
        multipart_id = upload_marker.removeprefix("multipart:") if upload_marker.startswith("multipart:") else ""
        try:
            metadata = await provider.stat(session["object_key"])
            if multipart_id and metadata is None:
                # The browser never supplies ETags. The storage provider lists
                # verified part sizes and ETags before composing an object.
                try:
                    metadata = await provider.finish_multipart(
                        session["object_key"], multipart_id,
                        expected_size=int(session["expected_size"]), part_size=PART_BYTES,
                    )
                except ValueError as exc:
                    raise HTTPException(409, str(exc)) from exc
        except HTTPException:
            raise
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
            await execute("UPDATE upload_sessions SET status='rejected' WHERE id=? AND status='uploaded'", (session_id,))
            raise HTTPException(422, "Uploaded object size did not match the authorized upload.")
        if metadata.content_type.lower() != str(session["expected_content_type"]).lower():
            await execute("UPDATE upload_sessions SET status='rejected' WHERE id=? AND status='uploaded'", (session_id,))
            raise HTTPException(422, "Uploaded object content type did not match the authorized upload.")
        project_id, video_id, job_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        timestamp = _now().isoformat()
        expires = source_media_expiry(user, at=_now()).isoformat()
        route = resolve_stage1_route(str(session["language"]), str(user["id"]))
        payload = json.dumps({"video_id": video_id, **route}, separators=(",", ":"))

        async def persist(db) -> None:
            lock = " FOR UPDATE" if get_settings().normalized_database_backend == "postgres" else ""
            cursor = await db.execute("SELECT status FROM upload_sessions WHERE id=? AND user_id=?" + lock, (session_id, user["id"]))
            locked = await cursor.fetchone()
            if not locked or locked["status"] != "uploaded":
                raise RuntimeError("Upload session was already consumed.")
            await db.execute("INSERT INTO projects VALUES (?, ?, ?, '', 'queued', 0, 'queued', ?, ?, NULL, ?, ?)", (project_id, user["id"], session["title"], session["language"], session["category"], timestamp, timestamp))
            await db.execute("INSERT INTO videos(id,project_id,original_filename,duration,width,height,file_size,file_path,object_generation,status,created_at,expires_at) VALUES (?,?,?,0,0,0,?,?,?,'uploaded',?,?)", (video_id, project_id, session["original_filename"], metadata.size, session["object_key"], metadata.generation, timestamp, expires))
            await db.execute("INSERT INTO jobs(id,user_id,project_id,export_id,kind,status,progress,stage,message,error,created_at,updated_at) VALUES (?,?,?,NULL,'process_video','queued',0,'queued','Waiting to start',NULL,?,?)", (job_id, user["id"], project_id, timestamp, timestamp))
            await db.execute("INSERT INTO job_payloads(job_id,payload_json,created_at,updated_at) VALUES (?,?,?,?)", (job_id, payload, timestamp, timestamp))
            await db.execute("UPDATE upload_sessions SET status='consumed',object_generation=?,project_id=?,job_id=?,consumed_at=? WHERE id=? AND status='uploaded'", (metadata.generation, project_id, job_id, timestamp, session_id))

        try:
            await run_in_transaction(persist, operation_name="complete direct upload")
            await get_job_launcher().launch(job_id)
        except JobLaunchError as exc:
            await execute("UPDATE jobs SET status='failed',stage='launch_failed',error='Media job launch failed',failed_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, job_id))
            raise HTTPException(503, "Video was stored safely, but processing could not start. Retry shortly.") from exc
        return {"project_id": project_id, "job_id": job_id, "status": "queued"}

    finally:
        # On successful persistence this is a no-op because status=consumed.
        # On validation/provider failures the session may be retried safely.
        await execute(
            "UPDATE upload_sessions SET status='initiated' "
            "WHERE id=? AND user_id=? AND status='uploaded'",
            (session_id, user["id"]),
        )



@router.post("/imports/youtube", status_code=202)
async def import_youtube(body: YouTubeImportRequest, user: dict = Depends(current_user)) -> dict[str, Any]:
    """Queue one creator-authorized YouTube video for the existing media pipeline."""
    if requires_verification_for_processing(user):
        raise HTTPException(
            403,
            {"message": "Verify your email before starting AI processing.", "code": "EMAIL_VERIFICATION_REQUIRED"},
        )
    limits = await project_routes.get_usage_for(user)
    if limits.shorts_remaining <= 0:
        raise HTTPException(
            402,
            "No AI Short creation credits remain in this plan. Existing Shorts can still be edited, exported and re-exported.",
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
    expires = source_media_expiry(user, at=_now()).isoformat()
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

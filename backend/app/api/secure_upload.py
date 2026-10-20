from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.api import routes as project_routes
from app.core.config import get_settings
from app.core.database import execute
from app.schemas.api import ProjectOut
from app.services.auth import current_user
from app.services.jobs import create_job, dispatch_job, utcnow
from app.services.hinglish_stage1_routing import resolve_stage1_route
from app.services.media_retention import source_media_expiry
from app.services.upload_scanner import UploadMalwareDetected, UploadScannerUnavailable, scan_upload
from app.services.video import save_upload


router = APIRouter()
security_logger = logging.getLogger("clipkaro.security")


@router.post("/projects/upload", response_model=ProjectOut, status_code=201)
async def upload_project(
    tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form("Untitled video"),
    language: str = Form("auto"),
    category: str = Form("auto"),
    user: dict = Depends(current_user),
) -> ProjectOut:
    """Quarantine -> scan -> persist -> enqueue.

    No project, job, Karo Minute reservation, FFprobe, ASR or render work exists
    until the upload passes the security boundary. In production worker mode the
    API stops after durable enqueue; Whisper/FFmpeg execute in the worker service.
    """
    settings = get_settings()
    limits = await project_routes.get_usage_for(user)
    if limits.shorts_remaining <= 0:
        raise HTTPException(
            402,
            "No AI Short creation credits remain in this plan. Existing Shorts can still be edited, exported and re-exported.",
        )
    project_id, video_id = str(uuid.uuid4()), str(uuid.uuid4())
    ext = Path(file.filename or "video.mp4").suffix.lower()
    destination = settings.upload_dir / f"{video_id}{ext}"
    original_name = Path(file.filename or "video").name

    size = await save_upload(file, destination)
    try:
        scan = await scan_upload(destination)
    except UploadMalwareDetected as exc:
        destination.unlink(missing_ok=True)
        security_logger.warning(
            "Rejected uploaded file user_id=%s filename=%s signature=%s",
            user.get("id"), original_name[:160], exc.signature[:160],
        )
        raise HTTPException(422, "The uploaded video failed ClipKaro's security scan.") from exc
    except UploadScannerUnavailable as exc:
        destination.unlink(missing_ok=True)
        security_logger.error("Upload scanner unavailable; blocked user_id=%s", user.get("id"))
        raise HTTPException(503, "Video security scanning is temporarily unavailable. Please retry shortly.") from exc

    timestamp = utcnow()
    expires = source_media_expiry(user, at=project_routes.now()).isoformat()
    route = resolve_stage1_route(language, str(user["id"]))
    try:
        await execute(
            "INSERT INTO projects VALUES (?, ?, ?, '', 'queued', 0, 'queued', ?, ?, NULL, ?, ?)",
            (project_id, user["id"], title[:120], language, category, timestamp, timestamp),
        )
        await execute(
            "INSERT INTO videos(id,project_id,original_filename,duration,width,height,file_size,file_path,status,created_at,expires_at) VALUES (?, ?, ?, 0, 0, 0, ?, ?, 'uploaded', ?, ?)",
            (video_id, project_id, original_name, size, str(destination), timestamp, expires),
        )
        job_id = await create_job(
            user["id"], "process_video", project_id=project_id,
            payload={"video_id": video_id, **route},
        )
    except Exception:
        # A scanned file without a durable job is useless and could otherwise
        # become a storage leak/ghost project. Project deletion cascades DB rows;
        # no minute reservation exists yet because the video is still uploaded.
        try:
            await execute("DELETE FROM projects WHERE id=?", (project_id,))
        finally:
            destination.unlink(missing_ok=True)
        raise

    # Development/tests retain BackgroundTasks. Production worker mode makes
    # this a no-op because the durable queue is consumed by `python -m app.worker`.
    await dispatch_job(tasks, project_routes._process_project, job_id, project_id, video_id, user, route["asr_route"])
    await project_routes.audit(
        user["id"], "project.uploaded", "project", project_id,
        {"bytes": size, "security_scan": scan.get("status"), "scan_engine": scan.get("engine")},
    )
    return ProjectOut(
        id=project_id,
        title=title[:120],
        status="queued",
        stage="queued",
        video_id=video_id,
        job_id=job_id,
        created_at=timestamp,
        updated_at=timestamp,
    )

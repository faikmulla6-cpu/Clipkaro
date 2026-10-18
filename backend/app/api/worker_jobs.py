from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api import routes as project_routes
from app.core.config import get_settings
from app.core.database import UsageQuotaExceeded, distributed_advisory_lock, execute, fetch_all, fetch_one
from app.schemas.api import AnalyseRequest, ExportOut, ExportRequest, ProjectOut, TranscriptCorrectionRequest
from app.services.auth import current_user
from app.services.content_pack import _row_to_response, generate_content_pack, persist_content_pack
from app.services.jobs import create_job, dispatch_job, update_job
from app.services.hinglish_stage1_routing import resolve_stage1_route
from app.services.transcript_review import (
    _hook_for_clip, _text_for_clip, effective_segments_for_video, reset_correction,
    review_payload, save_correction,
)
from app.services.storage_paths import confined_upload_path
from app.services.storage import get_storage_provider, validate_object_key


router = APIRouter()
MAX_REPROCESS_ATTEMPTS_PER_24H = 3
BRAND_KIT_PLANS = {"creator", "growth", "pro", "agency"}


async def _source_state(video: dict | None, user_id: str) -> str:
    """Distinguish deleted sources from temporary object-store errors.

    A storage timeout is NOT evidence that a paid user's video expired.
    Keep render/reprocess access fail-closed until a successful HEAD confirms
    the object, but give the project page an accurate verification state.
    """
    if not video:
        return "missing"
    if str(video.get("status") or "") == "expired":
        return "expired"
    settings = get_settings()
    if settings.normalized_storage_backend == "gcs":
        try:
            key = validate_object_key(
                str(video.get("file_path") or ""), expected_prefix=f"users/{user_id}"
            )
        except ValueError:
            return "missing"
        for attempt in range(2):
            try:
                metadata = await asyncio.wait_for(
                    get_storage_provider().stat(key), timeout=10
                )
                if metadata is None:
                    return "missing"
                generation = str(video.get("object_generation") or "")
                return "available" if not generation or metadata.generation == generation else "unverified"
            except Exception as exc:
                if attempt:
                    # Never turn transient Backblaze/Cloudflare connectivity
                    # issues into a permanent "your upload expired" claim.
                    import logging
                    logging.getLogger("clipkaro.source").warning(
                        "Object-storage source check failed after retry: %s",
                        type(exc).__name__,
                    )
                    return "unverified"
                await asyncio.sleep(0.25)
        return "unverified"
    path = confined_upload_path(video.get("file_path"))
    return "available" if path is not None and path.is_file() else "missing"


async def _source_available(video: dict | None, user_id: str) -> bool:
    """Backwards-compatible, fail-closed gate for export/re-analysis."""
    return await _source_state(video, user_id) == "available"


async def _require_source_available(video: dict | None, user_id: str) -> None:
    state = await _source_state(video, user_id)
    if state == "available":
        return
    if state == "unverified":
        raise HTTPException(
            503,
            "ClipKaro cannot verify the source video in private storage right now. Please retry shortly.",
            headers={"Retry-After": "5"},
        )
    raise HTTPException(
        410, "The original source video is no longer available in private storage."
    )


async def _active_export_for_clip(clip_id: str, user_id: str) -> dict | None:
    return await fetch_one(
        """SELECT e.id,e.status,j.id job_id FROM exports e
           LEFT JOIN jobs j ON j.export_id=e.id AND j.kind='render_export'
           WHERE e.clip_id=? AND e.user_id=? AND e.status IN ('queued','processing')
           ORDER BY e.created_at DESC LIMIT 1""",
        (clip_id, user_id),
    )


async def _active_export_for_user(user_id: str) -> dict | None:
    return await fetch_one(
        """SELECT id,status FROM exports
           WHERE user_id=? AND status IN ('queued','processing')
           ORDER BY created_at DESC LIMIT 1""",
        (user_id,),
    )


async def _content_pack_context(project_id: str, user_id: str) -> tuple[dict, list[dict], list[dict], str]:
    project = await fetch_one(
        """SELECT p.*,v.id video_id FROM projects p
           LEFT JOIN videos v ON v.project_id=p.id
           WHERE p.id=? AND p.user_id=?""",
        (project_id, user_id),
    )
    if not project:
        raise HTTPException(404, "Project not found.")
    if project.get("status") != "ready":
        raise HTTPException(409, "Content Pack is available after ClipKaro finishes finding clips.")
    transcript, segments = await effective_segments_for_video(project.get("video_id"))
    clips = await fetch_all(
        "SELECT * FROM clips WHERE video_id=? AND status<>'superseded' ORDER BY score DESC",
        (project.get("video_id"),),
    )
    for clip in clips:
        clip["score_breakdown"] = json.loads(clip.pop("score_breakdown_json") or "{}")
        clip["transcript_text"] = _text_for_clip(segments, float(clip["start_time"]), float(clip["end_time"]))
        clip["hook"] = _hook_for_clip(segments, float(clip["start_time"]), float(clip["end_time"]), str(clip.get("hook") or ""))
    if not segments or not clips:
        raise HTTPException(409, "Content Pack needs a verified transcript and at least one clip.")
    return project, clips, segments, str((transcript or {}).get("language") or project.get("language") or "auto")


async def _mark_project_enqueue_failed(project_id: str, reason: str) -> None:
    detail = reason[:700]
    await execute(
        "UPDATE projects SET status='failed',stage='failed',error=?,updated_at=? WHERE id=?",
        (detail, project_routes.utcnow(), project_id),
    )


async def _recent_forced_reprocess_count(project_id: str) -> int:
    """Count user-requested re-analysis jobs without relying on SQLite JSON1."""
    cutoff = (project_routes.now() - timedelta(hours=24)).isoformat()
    rows = await fetch_all(
        """SELECT COALESCE(p.payload_json,'{}') payload_json FROM jobs j
           LEFT JOIN job_payloads p ON p.job_id=j.id
           WHERE j.project_id=? AND j.kind='process_video' AND j.created_at>=?""",
        (project_id, cutoff),
    )
    count = 0
    for row in rows:
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("force_transcribe") is True:
            count += 1
    return count


async def _enqueue_project_job(
    *,
    tasks: BackgroundTasks,
    user: dict,
    kind: str,
    project_id: str,
    video: dict,
    force_transcribe: bool = False,
) -> str:
    try:
        project = await fetch_one("SELECT language FROM projects WHERE id=? AND user_id=?", (project_id, user["id"]))
        route = resolve_stage1_route(str((project or {}).get("language") or "auto"), str(user["id"]))
        job_id = await create_job(
            user["id"], kind, project_id=project_id,
            payload={"video_id": video["id"], "force_transcribe": bool(force_transcribe), **route},
        )
    except Exception:
        # Never leave a project claiming to be queued when there is no durable
        # worker job that can make progress. Existing finalized usage remains
        # finalized; only a still-reserved retry is released by the failed-state trigger.
        await _mark_project_enqueue_failed(
            project_id,
            "ClipKaro could not enqueue this processing job safely. Retry from the project page.",
        )
        raise
    await dispatch_job(
        tasks, project_routes._process_project,
        job_id, project_id, video["id"], user, route["asr_route"], bool(force_transcribe),
    )
    return job_id


@router.get("/projects/{project_id}")
async def project_detail(project_id: str, tasks: BackgroundTasks, user: dict = Depends(current_user)) -> dict:
    project = await fetch_one(
        """SELECT p.*,v.id video_id,v.duration,v.width,v.height,v.original_filename,
          (SELECT t.language FROM transcripts t WHERE t.video_id=v.id ORDER BY t.created_at DESC LIMIT 1) detected_language
          FROM projects p LEFT JOIN videos v ON v.project_id=p.id WHERE p.id=? AND p.user_id=?""",
        (project_id, user["id"]),
    )
    if not project:
        raise HTTPException(404, "Project not found.")
    transcript = await fetch_one(
        "SELECT * FROM transcripts WHERE video_id=? ORDER BY created_at DESC LIMIT 1",
        (project["video_id"],),
    )
    corrections = await fetch_all("SELECT * FROM transcript_corrections WHERE transcript_id=?", (transcript["id"],)) if transcript else []
    review = review_payload(transcript, corrections) if transcript else {"summary": {"flagged": 0, "corrected": 0, "reviewed": 0, "remaining": 0}, "segments": []}
    _, segments = await effective_segments_for_video(project["video_id"])
    settings = get_settings()
    state = project_routes.transcript_state(
        segments, settings.effective_require_asr_consensus, settings.effective_require_forced_alignment,
    )
    project["pipeline_version"] = project_routes.PIPELINE_VERSION
    project["transcript_state"] = state
    project["transcript_review"] = review["summary"]
    source = await fetch_one("SELECT file_path,status,object_generation FROM videos WHERE id=?", (project["video_id"],))
    source_state = await _source_state(source, str(user["id"]))
    source_available = source_state == "available"
    project["source_available"] = source_available
    project["source_state"] = source_state
    if not state["current"] and project.get("status") not in {"queued", "processing"}:
        video = await fetch_one("SELECT * FROM videos WHERE id=?", (project["video_id"],))
        active_export = await fetch_one(
            """SELECT e.id FROM exports e JOIN clips c ON c.id=e.clip_id
               WHERE c.video_id=? AND e.status IN ('queued','processing') LIMIT 1""",
            (project["video_id"],),
        )
        if active_export:
            # Opening an old project must never mutate the transcript/clip set
            # underneath an export that is already rendering. Explicit
            # re-analysis has the same guard. Preserve history and let the user
            # retry the upgrade once the export has reached a terminal state.
            project["upgrade_blocked"] = "active_export"
            clips = await fetch_all(
                "SELECT * FROM clips WHERE video_id=? AND status<>'superseded' ORDER BY score DESC",
                (project["video_id"],),
            )
        elif video and source_available:
            await execute(
                "UPDATE projects SET status='queued',progress=0,stage='upgrading',error=NULL,updated_at=? WHERE id=?",
                (project_routes.utcnow(), project_id),
            )
            job_id = await _enqueue_project_job(
                tasks=tasks, user=user, kind="upgrade_pipeline", project_id=project_id, video=video,
            )
            project.update({"status": "queued", "progress": 0, "stage": "upgrading", "job_id": job_id})
            clips = []
        else:
            # The source-retention policy may outlive derived project data.
            # Preserve the historical moments instead of creating a doomed job.
            project["upgrade_blocked"] = "source_unverified" if source_state == "unverified" else "source_expired"
            clips = await fetch_all(
                "SELECT * FROM clips WHERE video_id=? AND status<>'superseded' ORDER BY score DESC",
                (project["video_id"],),
            )
    else:
        clips = await fetch_all(
            "SELECT * FROM clips WHERE video_id=? AND status<>'superseded' ORDER BY score DESC",
            (project["video_id"],),
        )
    for clip in clips:
        clip["score_breakdown"] = json.loads(clip.pop("score_breakdown_json") or "{}")
        clip["transcript_text"] = _text_for_clip(segments, float(clip["start_time"]), float(clip["end_time"]))
        clip["hook"] = _hook_for_clip(segments, float(clip["start_time"]), float(clip["end_time"]), str(clip.get("hook") or ""))
    project["clips"] = clips
    return project


@router.get("/projects/{project_id}/content-pack")
async def get_content_pack(project_id: str, user: dict = Depends(current_user)) -> dict:
    project = await fetch_one("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user["id"]))
    if not project:
        raise HTTPException(404, "Project not found.")
    row = await fetch_one("SELECT * FROM content_packs WHERE project_id=?", (project_id,))
    return _row_to_response(row)


@router.get("/projects/{project_id}/transcript-review")
async def get_transcript_review(project_id: str, user: dict = Depends(current_user)) -> dict:
    project = await fetch_one(
        """SELECT p.id,v.id video_id FROM projects p JOIN videos v ON v.project_id=p.id
           WHERE p.id=? AND p.user_id=?""",
        (project_id, user["id"]),
    )
    if not project:
        raise HTTPException(404, "Project not found.")
    transcript = await fetch_one("SELECT * FROM transcripts WHERE video_id=? ORDER BY created_at DESC LIMIT 1", (project["video_id"],))
    if not transcript:
        return {"language": "auto", "summary": {"flagged": 0, "corrected": 0, "reviewed": 0, "remaining": 0}, "segments": []}
    corrections = await fetch_all("SELECT * FROM transcript_corrections WHERE transcript_id=?", (transcript["id"],))
    return review_payload(transcript, corrections)


@router.patch("/projects/{project_id}/transcript-review/{segment_index}")
async def patch_transcript_review(
    project_id: str,
    segment_index: int,
    body: TranscriptCorrectionRequest,
    user: dict = Depends(current_user),
) -> dict:
    try:
        result = await save_correction(project_id, str(user["id"]), segment_index, body.text)
        await project_routes.audit(user["id"], "transcript.corrected", "project", project_id, {"segment_index": segment_index})
        return result
    except PermissionError:
        raise HTTPException(404, "Project not found.")
    except LookupError:
        raise HTTPException(404, "Transcript not found.")
    except IndexError:
        raise HTTPException(404, "Transcript segment not found.")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/projects/{project_id}/transcript-review/{segment_index}")
async def delete_transcript_review(project_id: str, segment_index: int, user: dict = Depends(current_user)) -> dict:
    try:
        result = await reset_correction(project_id, str(user["id"]), segment_index)
        await project_routes.audit(user["id"], "transcript.correction_reset", "project", project_id, {"segment_index": segment_index})
        return result
    except PermissionError:
        raise HTTPException(404, "Project not found.")
    except LookupError:
        raise HTTPException(404, "Transcript not found.")
    except IndexError:
        raise HTTPException(404, "Transcript segment not found.")


@router.post("/projects/{project_id}/content-pack", status_code=201)
async def create_content_pack(project_id: str, user: dict = Depends(current_user)) -> dict:
    existing = await fetch_one("SELECT * FROM content_packs WHERE project_id=? AND status='ready'", (project_id,))
    if existing:
        return _row_to_response(existing)
    try:
        project, clips, segments, language = await _content_pack_context(project_id, str(user["id"]))
        payload = generate_content_pack(project, clips, segments, language)
        result = await persist_content_pack(project_id, payload)
        await project_routes.audit(user["id"], "content_pack.generated", "project", project_id, {"clips": len(clips)})
        return result
    except HTTPException:
        raise
    except Exception as exc:
        await persist_content_pack(project_id, {"error": "Content Pack couldn't be generated. Try again."}, status="failed")
        raise HTTPException(502, "Content Pack couldn't be generated. Try again.") from exc


@router.post("/projects/{project_id}/reprocess", response_model=ProjectOut, status_code=202)
async def reprocess_project(
    project_id: str,
    body: AnalyseRequest,
    tasks: BackgroundTasks,
    user: dict = Depends(current_user),
) -> ProjectOut:
    video = await fetch_one(
        """SELECT v.* FROM videos v JOIN projects p ON p.id=v.project_id
           WHERE p.id=? AND p.user_id=?""",
        (project_id, user["id"]),
    )
    if not video:
        raise HTTPException(404, "Project not found.")
    await _require_source_available(video, str(user["id"]))
    project_state = await fetch_one("SELECT status FROM projects WHERE id=? AND user_id=?", (project_id, user["id"]))
    if project_state and project_state.get("status") in {"queued", "processing"}:
        raise HTTPException(409, "This project is already being processed. Wait for it to finish before re-analysing.")
    active_export = await fetch_one(
        """SELECT e.id FROM exports e JOIN clips c ON c.id=e.clip_id
           WHERE c.video_id=? AND e.status IN ('queued','processing') LIMIT 1""",
        (video["id"],),
    )
    if active_export:
        raise HTTPException(409, "Wait for the current export to finish before re-analysing this project.")
    if await _recent_forced_reprocess_count(project_id) >= MAX_REPROCESS_ATTEMPTS_PER_24H:
        raise HTTPException(
            429,
            "This video has reached its language re-analysis safety limit. Try again after 24 hours.",
            headers={"Retry-After": "3600"},
        )
    language = body.language if body.language in {"auto", "en", "hi", "hinglish", "mr"} else "auto"
    await execute(
        "UPDATE projects SET language=?,status='queued',progress=0,stage='queued',error=NULL,updated_at=? WHERE id=?",
        (language, project_routes.utcnow(), project_id),
    )
    job_id = await _enqueue_project_job(
        tasks=tasks, user=user, kind="process_video", project_id=project_id, video=video,
        force_transcribe=True,
    )
    project = await fetch_one("SELECT * FROM projects WHERE id=?", (project_id,))
    return ProjectOut(**project, video_id=video["id"], job_id=job_id)


@router.post("/clips/{clip_id}/export", response_model=ExportOut, status_code=202)
async def export_clip(
    clip_id: str,
    body: ExportRequest,
    tasks: BackgroundTasks,
    user: dict = Depends(current_user),
) -> ExportOut:
    clip = await fetch_one(
        """SELECT c.*,p.user_id,p.id project_id FROM clips c
           JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
           WHERE c.id=? AND p.user_id=?""",
        (clip_id, user["id"]),
    )
    if not clip:
        raise HTTPException(404, "Clip not found.")
    if clip.get("status") == "superseded":
        raise HTTPException(409, "This moment belongs to an earlier analysis and cannot be exported again.")

    _, segments = await effective_segments_for_video(clip["video_id"])
    settings = get_settings()
    state = project_routes.transcript_state(
        segments, settings.effective_require_asr_consensus, settings.effective_require_forced_alignment,
    )
    if not state["export_safe"]:
        project = await fetch_one("SELECT status FROM projects WHERE id=?", (clip["project_id"],))
        if not project or project["status"] not in {"queued", "processing"}:
            video = await fetch_one("SELECT * FROM videos WHERE id=?", (clip["video_id"],))
            if not video:
                raise HTTPException(409, "This project no longer has a source video to upgrade.")
            await _require_source_available(video, str(user["id"]))
            await execute(
                "UPDATE projects SET status='queued',progress=0,stage='upgrading',error=NULL,updated_at=? WHERE id=?",
                (project_routes.utcnow(), clip["project_id"]),
            )
            await _enqueue_project_job(
                tasks=tasks, user=user, kind="upgrade_pipeline",
                project_id=clip["project_id"], video=video,
            )
        raise HTTPException(
            409,
            f"This project used an older AI pipeline ({state['reason']}). Automatic reprocessing has started; export the new verified clips when ready.",
        )

    # Serialize export creation for this user+clip across all API containers.
    # The reservation trigger remains the quota authority; this lock prevents
    # rapid double taps, retries, or two open tabs from reserving duplicate
    # renders before either request can observe the other.
    lock_key = f"clipkaro:export:{user['id']}:{clip_id}"
    async with distributed_advisory_lock(lock_key):
        active_export = await _active_export_for_clip(clip_id, str(user["id"]))
        if active_export:
            raise HTTPException(
                409,
                "This Short is already rendering. Wait for it to finish before starting another render.",
            )

        limits = await project_routes.get_usage_for(user)
        active_plan = limits.plan
        if not limits.unlimited_exports and limits.exports_remaining <= 0:
            if await _active_export_for_user(str(user["id"])):
                raise HTTPException(
                    409,
                    "Another Short is currently rendering and has reserved your last Free export. Wait for it to finish, then try again.",
                )
            raise HTTPException(
                402,
                f"You've used all {limits.exports_limit} Short exports included in Free. Upgrade for unlimited exports and re-exports.",
            )
        if body.resolution == "1080p" and active_plan == "free":
            raise HTTPException(403, "1080p export is included with every paid ClipKaro plan.")

        # Entitlements are server-authoritative. Free exports always carry the
        # ClipKaro watermark even if a modified client sends watermark=false;
        # paid plans may choose it, but the normal UI defaults it off.
        effective_watermark = True if active_plan == "free" else bool(body.watermark)
        effective_body = body.model_copy(update={"watermark": effective_watermark})

        video = await fetch_one("SELECT * FROM videos WHERE id=?", (clip["video_id"],))
        if not video:
            raise HTTPException(409, "This clip no longer has a source video to render.")
        await _require_source_available(video, str(user["id"]))

        # If the v2 rollout is enabled, verify the exact authorized plan
        # BEFORE inserting an exports row. Never reserve a Free export for
        # a preview that has not completed, or quietly use a different crop.
        if body.layout_mode != "classic":
            from app.api.smart_layout_v2 import enabled_for_user as smart_v2_enabled
            if smart_v2_enabled(str(user["id"])):
                from app.api.smart_layout_v2 import _cached, _identity
                versioned_clip = {
                    **video, "clip_id": clip_id, "video_id": clip["video_id"],
                    "project_id": clip["project_id"],
                    "start_time": clip["start_time"], "end_time": clip["end_time"],
                }
                identity = _identity(versioned_clip, str(user["id"]))
                analyzed = await _cached(versioned_clip, identity)
                if not analyzed:
                    raise HTTPException(
                        409,
                        "Analyze the selected Smart Layout in the editor before exporting. No export allowance was consumed.",
                    )
                if body.layout_mode not in analyzed["plans"]:
                    raise HTTPException(409, "The selected Smart Layout has no matching analysis.")

        brand = None
        if effective_body.brand_kit_id:
            if active_plan not in BRAND_KIT_PLANS:
                raise HTTPException(403, "Brand kits start on the Creator plan.")
            brand = await fetch_one(
                "SELECT * FROM brand_kits WHERE id=? AND user_id=?",
                (effective_body.brand_kit_id, user["id"]),
            )
            if not brand:
                raise HTTPException(404, "Brand kit not found.")

        export_id = str(uuid.uuid4())
        cloud_storage = settings.normalized_storage_backend == "gcs"
        output_key = f"users/{user['id']}/exports/{export_id}/clip.mp4"
        output = settings.export_dir / f"{export_id}.mp4"
        output_record = output_key if cloud_storage else str(output)
        created = project_routes.utcnow()
        expires = (project_routes.now() + timedelta(hours=settings.file_expiry_hours)).isoformat()
        try:
            await execute(
                """INSERT INTO exports(id,clip_id,user_id,output_path,resolution,aspect_ratio,caption_style,watermark,
                   status,progress,error,created_at,expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, ?, ?)""",
                (
                    export_id, clip_id, user["id"], output_record, effective_body.resolution,
                    effective_body.aspect_ratio, effective_body.caption_style, int(effective_body.watermark), created, expires,
                ),
            )
        except UsageQuotaExceeded as exc:
            raise HTTPException(402, str(exc)) from exc

        try:
            # Persist the normalized, entitlement-safe request before the job
            # becomes visible to the isolated worker. Customization therefore
            # survives restarts without trusting client-only state.
            job_id = await create_job(
                user["id"], "render_export", export_id=export_id,
                payload={"request": effective_body.model_dump(mode="json")},
            )
        except Exception as exc:
            # The export row must reach a terminal failed state so the database
            # reservation trigger refunds the Short atomically. Deleting a
            # queued row directly would orphan its reservation on PostgreSQL.
            message = "ClipKaro could not create the render job. Your export allowance was not consumed."
            try:
                await execute("UPDATE exports SET status='failed',error=? WHERE id=?", (message, export_id))
            except Exception:
                project_routes.logger.exception("Could not release export reservation export_id=%s", export_id)
            if not cloud_storage:
                output.unlink(missing_ok=True)
            raise exc

        try:
            await dispatch_job(
                tasks, project_routes._render_export,
                job_id, export_id, clip, video, effective_body, output, brand,
            )
        except Exception as exc:
            # A launcher failure must immediately return the Free export allowance and
            # must not leave a queued job that the UI can mistake for progress.
            message = "ClipKaro could not start the render worker. Your export allowance was not consumed."
            await execute("UPDATE exports SET status='failed',error=? WHERE id=?", (message, export_id))
            await update_job(job_id, 0, "failed", message, "failed", "PROVIDER_TEMPORARY_FAILURE")
            raise HTTPException(503, message) from exc

        return ExportOut(id=export_id, job_id=job_id, status="queued", expires_at=expires)

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import tempfile
import uuid
from pathlib import Path

from app.api import routes as project_routes
from app.core.config import get_settings
from app.core.database import close_database, execute, fetch_one, init_db
from app.schemas.api import ExportRequest
from app.services.hinglish_stage1_routing import persisted_stage1_route
from app.services.india_quality import caption_segments_for_export, effective_caption_position
from app.services.jobs import claim_job, heartbeat_job_claim, init_job_queue, release_claim, update_job, utcnow
from app.services.pipeline_provenance import transcript_state
from app.services.render_gate import render_short_limited
from app.services.rendering import create_edited_srt, create_srt, timed_words
from app.services.source_caption_detection import detect_burned_captions
from app.services.storage import get_storage_provider, validate_object_key
from app.services.transcript_review import effective_segments_for_video
from app.services.upload_scanner import UploadMalwareDetected, UploadScannerUnavailable, scan_upload
from app.services.youtube_import import YouTubeImportError, download_youtube_source
from app.services.youtube_worker_client import ingest_youtube_to_storage


logger = logging.getLogger("clipkaro.media_job")


async def _heartbeat(job_id: str) -> None:
    while True:
        await asyncio.sleep(20)
        await heartbeat_job_claim(job_id)


def _video_mp4(content_type: str) -> bool:
    return str(content_type or "").split(";", 1)[0].strip().lower() == "video/mp4"


def _source_content_type(path: Path) -> str:
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }.get(path.suffix.lower(), "application/octet-stream")


async def _render_export_durable(
    job: dict,
    export: dict,
    clip: dict,
    video: dict,
    request: ExportRequest,
    source: Path,
    output: Path,
    brand: dict | None,
    storage,
) -> None:
    """Render locally, persist to object storage, then expose the export as ready.

    The order is deliberate: a completed job must never advertise a download
    before the MP4 exists in durable private storage.
    """
    srt = output.with_suffix(".srt")
    try:
        await update_job(job["id"], 12, "preparing", "Preparing crop, captions and brand style")
        await execute(
            "UPDATE exports SET status='processing',progress=12,error=NULL WHERE id=?",
            (export["id"],),
        )

        transcript, segments = await effective_segments_for_video(video["id"])
        raw_segments = json.loads(transcript["segments_json"]) if transcript else []
        settings = get_settings()
        state = transcript_state(
            segments,
            settings.effective_require_asr_consensus,
            settings.effective_require_forced_alignment,
        )
        if not state["export_safe"]:
            raise RuntimeError(f"Export blocked by transcript safety gate: {state['reason']}.")

        source_text = " ".join(
            str(item.get("display_text") or item.get("text", "")).strip()
            for item in segments
            if float(item.get("end", 0)) > clip["start_time"]
            and float(item.get("start", 0)) < clip["end_time"]
        )
        normalize = lambda value: re.sub(r"\s+", " ", value or "").strip().casefold()
        caption_segments = caption_segments_for_export(
            segments,
            (transcript or {}).get("language", "auto"),
            india_quality_mode=request.india_quality_mode,
            caption_language_style=request.caption_language_style,
        )
        correction_in_clip = any(
            segment.get("corrected_text")
            and float(segment.get("end", 0)) > clip["start_time"]
            and float(segment.get("start", 0)) < clip["end_time"]
            for segment in segments
        )
        if correction_in_clip:
            reference = timed_words(raw_segments, clip["start_time"], clip["end_time"])
            create_edited_srt(
                source_text,
                clip["end_time"] - clip["start_time"],
                srt,
                reference,
                clip["start_time"],
            )
        elif transcript and normalize(clip.get("transcript_text")) == normalize(source_text):
            create_srt(caption_segments, clip["start_time"], clip["end_time"], srt)
        elif clip.get("transcript_text"):
            reference = timed_words(segments, clip["start_time"], clip["end_time"])
            create_edited_srt(
                clip["transcript_text"],
                clip["end_time"] - clip["start_time"],
                srt,
                reference,
                clip["start_time"],
            )

        await update_job(job["id"], 35, "rendering", "Rendering your social-ready video")
        await execute(
            "UPDATE exports SET status='processing',progress=35,error=NULL WHERE id=?",
            (export["id"],),
        )

        scan = await detect_burned_captions(source, float(video.get("duration") or clip["end_time"]))
        preserve_band = scan.get("band_start") if scan["detected"] else None
        if request.preserve_source_captions and preserve_band is None:
            preserve_band = 0.82
        # Creator choice is authoritative. Existing burned-in subtitles inform the
        # UI only; they never silently move the creator's requested caption placement.
        caption_position = effective_caption_position(
            request.india_quality_mode,
            request.preserve_source_captions,
            request.caption_position,
        )
        try:
            await render_short_limited(
                source,
                output,
                clip["start_time"],
                clip["end_time"],
                srt if srt.exists() else None,
                request.hook_text or clip["hook"],
                request.watermark,
                request.resolution,
                request.aspect_ratio,
                request.caption_style,
                (brand or {}).get("logo_text") or "",
                (brand or {}).get("primary_color") or "#DFFF57",
                request.focus_x,
                caption_position,
                [item.model_dump() for item in request.crop_keyframes],
                preserve_band,
                caption_x=request.caption_x,
                caption_y=request.caption_y,
                caption_scale=request.caption_scale,
                caption_alignment=request.caption_alignment,
            )
        except Exception as exc:
            # Keep the creator-facing failure generic, but preserve the actual
            # render exception in server logs so production failures are
            # diagnosable without exposing internals to the browser.
            logger.exception(
                "Export render failed job_id=%s export_id=%s error_type=%s",
                job["id"],
                export["id"],
                type(exc).__name__,
            )
            raise RuntimeError("EXPORT_FAILED") from exc

        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("EXPORT_FAILED")

        await update_job(job["id"], 92, "uploading", "Securing your MP4 in private storage")
        await execute(
            "UPDATE exports SET status='processing',progress=92,error=NULL WHERE id=?",
            (export["id"],),
        )

        output_key = validate_object_key(
            f"users/{job['user_id']}/exports/{export['id']}/clip.mp4",
            expected_prefix=f"users/{job['user_id']}/exports/{export['id']}",
        )
        expected_size = output.stat().st_size
        existing = await storage.stat(output_key)
        if existing:
            await storage.delete(output_key, generation=existing.generation or None)
        stored = await storage.upload(output, output_key, content_type="video/mp4")

        verified = await storage.stat(output_key)
        if verified is None or verified.size != expected_size or not _video_mp4(verified.content_type):
            raise RuntimeError("EXPORT_FAILED")

        generation = verified.generation or stored.generation
        await execute(
            """UPDATE exports
               SET output_path=?,object_generation=?,status='ready',progress=100,error=NULL
               WHERE id=?""",
            (output_key, generation, export["id"]),
        )
        await execute(
            "UPDATE clips SET status='exported',updated_at=? WHERE id=?",
            (utcnow(), clip["id"]),
        )

        try:
            await project_routes.audit(job["user_id"], "export.completed", "export", export["id"])
        except Exception:
            logger.exception("Export audit write failed export_id=%s", export["id"])

        await update_job(job["id"], 100, "ready", "Your Short is ready to download", "completed")
    finally:
        srt.unlink(missing_ok=True)


async def _scan_source(source: Path, storage=None, source_key: str = "", generation: str | None = None) -> None:
    try:
        await scan_upload(source)
    except UploadMalwareDetected:
        if storage is not None and source_key:
            await storage.delete(source_key, generation=generation)
        raise RuntimeError("MEDIA_VALIDATION_FAILED")
    except UploadScannerUnavailable as exc:
        raise RuntimeError("MEDIA_VALIDATION_FAILED") from exc


async def _run_youtube_import(job: dict, scratch: Path, storage) -> None:
    payload = job.get("payload") or {}
    project_id = str(job.get("project_id") or "")
    video_id = str(payload.get("video_id") or "")
    user = await fetch_one("SELECT * FROM users WHERE id=?", (job["user_id"],))
    video = await fetch_one("SELECT * FROM videos WHERE id=? AND project_id=?", (video_id, project_id))
    if not user or not video or not project_id:
        raise RuntimeError("Project worker input no longer exists.")

    await update_job(job["id"], 3, "importing", "Checking your YouTube video and plan limits")
    source_key = validate_object_key(
        str(video.get("file_path") or ""),
        expected_prefix=f"users/{user['id']}/projects/{project_id}",
    )
    source: Path

    existing = await storage.stat(source_key) if video.get("object_generation") else None
    if existing and existing.size > 0:
        suffix = Path(str(video.get("original_filename") or "source.mp4")).suffix.lower() or ".mp4"
        source = scratch / "uploads" / f"{video_id}{suffix}"
        await storage.download(source_key, source, generation=video.get("object_generation"))
        await _scan_source(source, storage, source_key, video.get("object_generation"))
    else:
        canonical_url = str(payload.get("canonical_url") or "")
        limits = await project_routes.get_usage_for(user)
        active_plan = limits.plan
        max_minutes = project_routes.PLAN_MAX_SOURCE_MINUTES.get(
            active_plan, project_routes.PLAN_MAX_SOURCE_MINUTES["free"]
        )
        settings = get_settings()
        provider = settings.normalized_youtube_ingestion_provider
        max_bytes = int(settings.max_upload_mb) * 1024 * 1024
        if provider == "worker":
            imported = await ingest_youtube_to_storage(
                canonical_url,
                user_id=str(user["id"]),
                project_id=project_id,
                max_minutes=float(max_minutes),
                remaining_minutes=float(limits.processing_minutes_remaining),
                max_bytes=max_bytes,
                storage=storage,
                worker_url=settings.youtube_ingestion_worker_url,
                worker_secret=settings.youtube_ingestion_worker_secret,
                timeout_seconds=float(settings.youtube_ingestion_worker_timeout_seconds),
                upload_ttl_seconds=int(settings.youtube_ingestion_worker_upload_ttl_seconds),
            )
            durable_key = imported.object_key
            verified = imported.metadata
            generation = verified.generation
            suffix = ".mp4"
            source = scratch / "youtube" / f"source-{imported.video_id}.mp4"
            source.parent.mkdir(parents=True, exist_ok=True)
            try:
                await storage.download(durable_key, source, generation=generation or None)
                await update_job(job["id"], 6, "importing", "Securing the source for private AI processing")
                await _scan_source(source, storage, durable_key, generation or None)
            except Exception:
                await storage.delete(durable_key, generation=generation or None)
                raise
        else:
            imported = await asyncio.to_thread(
                download_youtube_source,
                canonical_url,
                scratch / "youtube",
                max_minutes=float(max_minutes),
                remaining_minutes=float(limits.processing_minutes_remaining),
                max_bytes=max_bytes,
                ingestion_provider=provider,
                socialkit_access_key=settings.socialkit_access_key,
                socialkit_api_base_url=settings.socialkit_api_base_url,
                socialkit_quality=settings.socialkit_quality,
                socialkit_poll_interval_seconds=float(settings.socialkit_poll_interval_seconds),
                socialkit_timeout_seconds=float(settings.socialkit_timeout_seconds),
                socialkit_download_timeout_seconds=float(settings.socialkit_download_timeout_seconds),
                socialkit_download_host_suffixes=settings.socialkit_download_host_suffixes,
            )
            source = imported.path
            await update_job(job["id"], 6, "importing", "Securing the source for private AI processing")
            await _scan_source(source)
            suffix = source.suffix.lower() if source.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"} else ".mp4"
            durable_key = validate_object_key(
                f"users/{user['id']}/projects/{project_id}/source/{uuid.uuid4().hex}{suffix}",
                expected_prefix=f"users/{user['id']}/projects/{project_id}",
            )
            stored = await storage.upload(source, durable_key, content_type=_source_content_type(source))
            verified = await storage.stat(durable_key)
            if verified is None or verified.size != source.stat().st_size or verified.size <= 0:
                await storage.delete(durable_key, generation=(verified or stored).generation if (verified or stored) else None)
                raise RuntimeError("MEDIA_VALIDATION_FAILED")
            generation = verified.generation or stored.generation
        try:
            await execute(
                """UPDATE videos SET original_filename=?,file_size=?,file_path=?,object_generation=?,status='uploaded'
                   WHERE id=? AND project_id=?""",
                (
                    f"youtube-{imported.video_id}{suffix}",
                    verified.size,
                    durable_key,
                    generation,
                    video_id,
                    project_id,
                ),
            )
        except Exception:
            # If persistence fails after the private object upload, remove the
            # unreferenced object so a retry cannot leak storage.
            await storage.delete(durable_key, generation=generation)
            raise
        source_key = durable_key
        if not bool(payload.get("title_is_custom")):
            await execute(
                "UPDATE projects SET title=?,updated_at=? WHERE id=?",
                (imported.title[:120], utcnow(), project_id),
            )
        video = await fetch_one("SELECT * FROM videos WHERE id=?", (video_id,)) or video

    route = persisted_stage1_route(payload)
    await project_routes._process_project(
        job["id"], project_id, video_id, user, route["asr_route"], False, source,
    )
    state = await fetch_one("SELECT status FROM projects WHERE id=?", (project_id,))
    if state and state.get("status") == "ready":
        return
    current_job = await fetch_one("SELECT status FROM jobs WHERE id=?", (job["id"],))
    if current_job and current_job.get("status") == "failed":
        return
    raise RuntimeError("PROVIDER_TEMPORARY_FAILURE")


async def _run(job: dict, scratch: Path) -> None:
    storage = get_storage_provider()
    if job["kind"] == "import_youtube":
        await _run_youtube_import(job, scratch, storage)
        return

    if job["kind"] in {"process_video", "upgrade_pipeline"}:
        project_id = str(job["project_id"])
        video_id = str((job.get("payload") or {}).get("video_id") or "")
        user = await fetch_one("SELECT * FROM users WHERE id=?", (job["user_id"],))
        video = await fetch_one("SELECT * FROM videos WHERE id=? AND project_id=?", (video_id, project_id))
        if not user or not video:
            raise RuntimeError("Project worker input no longer exists.")
        source_key = validate_object_key(str(video["file_path"]), expected_prefix=f"quarantine/{user['id']}") if str(video["file_path"]).startswith("quarantine/") else validate_object_key(str(video["file_path"]), expected_prefix=f"users/{user['id']}")
        source = scratch / "uploads" / (video_id + Path(video["original_filename"]).suffix.lower())
        await storage.download(source_key, source, generation=video.get("object_generation"))
        await _scan_source(source, storage, source_key, video.get("object_generation"))
        route = persisted_stage1_route(job.get("payload"))
        await project_routes._process_project(
            job["id"], project_id, video_id, user, route["asr_route"],
            bool((job.get("payload") or {}).get("force_transcribe", False)), source,
        )
        state = await fetch_one("SELECT status FROM projects WHERE id=?", (project_id,))
        if not state or state["status"] != "ready":
            # _process_project owns product-level validation and persists a
            # user-safe terminal failure. Do not replace that truth with the
            # serverless wrapper's generic provider category/progress=0 state.
            current_job = await fetch_one("SELECT status FROM jobs WHERE id=?", (job["id"],))
            if current_job and current_job.get("status") == "failed":
                return
            raise RuntimeError("PROVIDER_TEMPORARY_FAILURE")
        if state and state["status"] == "ready" and source_key.startswith("quarantine/"):
            durable_key = f"users/{user['id']}/projects/{project_id}/source/{uuid.uuid4().hex}{source.suffix}"
            stored = await storage.upload(source, durable_key, content_type="application/octet-stream")
            await execute("UPDATE videos SET file_path=?,object_generation=? WHERE id=?", (durable_key, stored.generation, video_id))
            await storage.delete(source_key, generation=video.get("object_generation"))
        return

    if job["kind"] == "post_karo_publish":
        publication_id = str((job.get("payload") or {}).get("publication_id") or "").strip()
        if not publication_id:
            raise RuntimeError("Post Karo worker input is incomplete.")
        # Post Karo deliberately reuses the isolated media runtime without
        # attaching jobs.export_id. A provider failure can therefore never
        # mutate a finished ClipKaro export into a failed export.
        from app.services.post_karo import run_publication_job
        await run_publication_job(job["id"], publication_id, scratch=scratch, storage=storage)
        return

    if job["kind"] == "render_export":
        export = await fetch_one("SELECT * FROM exports WHERE id=?", (job["export_id"],))
        payload = (job.get("payload") or {}).get("request")
        if not export or not isinstance(payload, dict):
            raise RuntimeError("Export worker input is incomplete.")
        request = ExportRequest(**payload)
        clip = await fetch_one(
            """SELECT c.*,p.user_id,p.id project_id FROM clips c JOIN videos v ON v.id=c.video_id
               JOIN projects p ON p.id=v.project_id WHERE c.id=? AND p.user_id=?""",
            (export["clip_id"], job["user_id"]),
        )
        video = await fetch_one("SELECT * FROM videos WHERE id=?", (clip["video_id"],)) if clip else None
        if not clip or not video:
            raise RuntimeError("Export source no longer exists.")

        if export.get("status") == "ready":
            try:
                ready_key = validate_object_key(
                    str(export.get("output_path") or ""),
                    expected_prefix=f"users/{job['user_id']}/exports/{export['id']}",
                )
                ready_object = await storage.stat(ready_key)
            except ValueError:
                ready_object = None
            if ready_object and ready_object.size > 0 and _video_mp4(ready_object.content_type):
                await update_job(job["id"], 100, "ready", "Your Short is ready to download", "completed")
                return

        source_key = validate_object_key(str(video["file_path"]), expected_prefix=f"users/{job['user_id']}")
        source = scratch / "uploads" / (video["id"] + Path(video["original_filename"]).suffix.lower())
        output = scratch / "exports" / f"{export['id']}.mp4"
        await storage.download(source_key, source, generation=video.get("object_generation"))
        brand = await fetch_one("SELECT * FROM brand_kits WHERE id=? AND user_id=?", (request.brand_kit_id, job["user_id"])) if request.brand_kit_id else None
        await _render_export_durable(job, export, clip, video, request, source, output, brand, storage)
        return
    raise RuntimeError("Unsupported media job kind.")


async def run_job(job_id: str, *, execution_id: str = "", worker_prefix: str = "serverless") -> int:
    """Execute one durable media job from any isolated serverless runtime.

    Cloud Run keeps its environment-variable entrypoint; Modal calls this
    function directly with the same PostgreSQL claim/idempotency authority.
    """
    job_id = str(job_id or "").strip()
    if not job_id:
        raise RuntimeError("JOB_ID is required; no other execution override is accepted.")
    await init_db()
    await init_job_queue()
    worker_id = f"{worker_prefix}:{socket.gethostname()}:{os.getpid()}"
    job = await claim_job(job_id, worker_id, execution_id=execution_id)
    if not job:
        await close_database()
        return 0
    heartbeat = asyncio.create_task(_heartbeat(job_id))
    try:
        with tempfile.TemporaryDirectory(prefix="clipkaro-") as directory:
            scratch = Path(directory)
            (scratch / "uploads").mkdir()
            (scratch / "exports").mkdir()
            await _run(job, scratch)
        return 0
    except Exception as exc:
        public_message = str(getattr(exc, "public_message", "") or "").strip()
        if isinstance(exc, YouTubeImportError):
            category = "YOUTUBE_IMPORT_FAILED"
        else:
            category = str(exc) if str(exc) in {"MEDIA_VALIDATION_FAILED", "EXPORT_FAILED"} else "PROVIDER_TEMPORARY_FAILURE"
        failure_message = public_message or "Media processing failed"

        if job.get("export_id"):
            current_export = await fetch_one("SELECT status FROM exports WHERE id=?", (job["export_id"],))
            if current_export and current_export.get("status") == "ready":
                try:
                    await update_job(job_id, 100, "ready", "Your Short is ready to download", "completed")
                    return 0
                except Exception:
                    logger.exception("Could not recover completed export job_id=%s", job_id)
                    return 1

        if job.get("project_id"):
            current_project = await fetch_one("SELECT status FROM projects WHERE id=?", (job["project_id"],))
            if current_project and current_project.get("status") == "ready":
                try:
                    await update_job(job_id, 100, "ready", "Project processing is complete", "completed")
                    return 0
                except Exception:
                    logger.exception("Could not recover completed project job_id=%s", job_id)
                    return 1

        await update_job(job_id, int(job.get("progress") or 0), "failed", failure_message, "failed", category)
        if job.get("project_id"):
            await execute("UPDATE projects SET status='failed',stage='failed',error=? WHERE id=?", (failure_message, job["project_id"]))
        if job.get("export_id"):
            await execute("UPDATE exports SET status='failed',error=? WHERE id=?", (category, job["export_id"]))
        return 1
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        await release_claim(job_id)
        await close_database()


async def main() -> int:
    job_id = os.environ.get("JOB_ID", "").strip()
    execution_id = os.environ.get("CLOUD_RUN_EXECUTION", "").strip()
    return await run_job(job_id, execution_id=execution_id, worker_prefix="cloud-run")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

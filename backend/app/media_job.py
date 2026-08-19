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
from app.services.jobs import claim_job, heartbeat_job_claim, init_job_queue, release_claim, update_job, utcnow
from app.services.pipeline_provenance import transcript_state
from app.services.render_gate import render_short_limited
from app.services.rendering import create_edited_srt, create_srt, timed_words
from app.services.source_caption_detection import detect_burned_captions
from app.services.storage import get_storage_provider, validate_object_key
from app.services.upload_scanner import UploadMalwareDetected, UploadScannerUnavailable, scan_upload


logger = logging.getLogger("clipkaro.media_job")


async def _heartbeat(job_id: str) -> None:
    while True:
        await asyncio.sleep(20)
        await heartbeat_job_claim(job_id)


def _video_mp4(content_type: str) -> bool:
    return str(content_type or "").split(";", 1)[0].strip().lower() == "video/mp4"


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

        transcript = await fetch_one(
            "SELECT segments_json FROM transcripts WHERE video_id=? ORDER BY created_at DESC LIMIT 1",
            (video["id"],),
        )
        segments = json.loads(transcript["segments_json"]) if transcript else []
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
        if transcript and normalize(clip.get("transcript_text")) == normalize(source_text):
            create_srt(segments, clip["start_time"], clip["end_time"], srt)
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
        # Creator choice is authoritative. Existing burned-in subtitles are still
        # detected and surfaced as a warning, but Lower/Above/Centre must render
        # exactly where the creator selected them.
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
            request.caption_position,
            [item.model_dump() for item in request.crop_keyframes],
            scan.get("band_start") if scan["detected"] else None,
        )

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

        if existing and existing.size == expected_size and _video_mp4(existing.content_type):
            stored = existing
        else:
            if existing:
                await storage.delete(output_key, generation=existing.generation or None)
            stored = await storage.upload(output, output_key, content_type="video/mp4")

        verified = await storage.stat(output_key)
        if verified is None or verified.size != expected_size or not _video_mp4(verified.content_type):
            raise RuntimeError("EXPORT_FAILED")

        generation = verified.generation or stored.generation
        # Persist the durable object key before exposing ready/completed. The
        # download route can now always create a signed URL for a real object.
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
            # Audit telemetry must not downgrade a verified downloadable export.
            logger.exception("Export audit write failed export_id=%s", export["id"])

        await update_job(job["id"], 100, "ready", "Your Short is ready to download", "completed")
    finally:
        srt.unlink(missing_ok=True)


async def _run(job: dict, scratch: Path) -> None:
    storage = get_storage_provider()
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
        try:
            await scan_upload(source)
        except UploadMalwareDetected:
            await storage.delete(source_key, generation=video.get("object_generation"))
            raise RuntimeError("MEDIA_VALIDATION_FAILED")
        except UploadScannerUnavailable as exc:
            raise RuntimeError("MEDIA_VALIDATION_FAILED") from exc
        route = persisted_stage1_route(job.get("payload"))
        await project_routes._process_project(
            job["id"], project_id, video_id, user, route["asr_route"],
            bool((job.get("payload") or {}).get("force_transcribe", False)), source,
        )
        state = await fetch_one("SELECT status FROM projects WHERE id=?", (project_id,))
        if not state or state["status"] != "ready":
            raise RuntimeError("PROVIDER_TEMPORARY_FAILURE")
        if state and state["status"] == "ready" and source_key.startswith("quarantine/"):
            durable_key = f"users/{user['id']}/projects/{project_id}/source/{uuid.uuid4().hex}{source.suffix}"
            stored = await storage.upload(source, durable_key, content_type="application/octet-stream")
            await execute("UPDATE videos SET file_path=?,object_generation=? WHERE id=?", (durable_key, stored.generation, video_id))
            await storage.delete(source_key, generation=video.get("object_generation"))
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

        # Recovery after a worker restart between durable upload and job
        # completion: verify the object and finish the job without rendering or
        # consuming another export reservation.
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
        category = str(exc) if str(exc) in {"MEDIA_VALIDATION_FAILED", "EXPORT_FAILED"} else "PROVIDER_TEMPORARY_FAILURE"
        await update_job(job_id, int(job.get("progress") or 0), "failed", "Media processing failed", "failed", category)
        if job.get("project_id"):
            await execute("UPDATE projects SET status='failed',stage='failed',error=? WHERE id=?", (category, job["project_id"]))
        if job.get("export_id"):
            current_export = await fetch_one("SELECT status FROM exports WHERE id=?", (job["export_id"],))
            # Never downgrade an already verified durable export because a
            # non-render side effect failed after publication.
            if not current_export or current_export.get("status") != "ready":
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

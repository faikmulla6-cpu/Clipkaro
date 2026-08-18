from __future__ import annotations

import asyncio
import json
import os
import socket
import tempfile
import uuid
from pathlib import Path

from app.api import routes as project_routes
from app.core.database import close_database, execute, fetch_one, init_db
from app.schemas.api import ExportRequest
from app.services.hinglish_stage1_routing import persisted_stage1_route
from app.services.jobs import claim_job, heartbeat_job_claim, init_job_queue, release_claim, update_job
from app.services.storage import get_storage_provider, validate_object_key
from app.services.upload_scanner import UploadMalwareDetected, UploadScannerUnavailable, scan_upload


async def _heartbeat(job_id: str) -> None:
    while True:
        await asyncio.sleep(20)
        await heartbeat_job_claim(job_id)


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
        source_key = validate_object_key(str(video["file_path"]), expected_prefix=f"users/{job['user_id']}")
        source = scratch / "uploads" / (video["id"] + Path(video["original_filename"]).suffix.lower())
        output = scratch / "exports" / f"{export['id']}.mp4"
        await storage.download(source_key, source, generation=video.get("object_generation"))
        brand = await fetch_one("SELECT * FROM brand_kits WHERE id=? AND user_id=?", (request.brand_kit_id, job["user_id"])) if request.brand_kit_id else None
        await project_routes._render_export(job["id"], export["id"], clip, video, request, output, brand, source)
        export_state = await fetch_one("SELECT status FROM exports WHERE id=?", (export["id"],))
        if not output.is_file() or not export_state or export_state["status"] != "ready":
            raise RuntimeError("EXPORT_FAILED")
        output_key = f"users/{job['user_id']}/exports/{export['id']}/clip.mp4"
        stored = await storage.upload(output, output_key, content_type="video/mp4")
        await execute("UPDATE exports SET output_path=?,object_generation=? WHERE id=?", (output_key, stored.generation, export["id"]))
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

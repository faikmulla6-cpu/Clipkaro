from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import socket
import tempfile
import uuid
from importlib import metadata
from pathlib import Path

from app.api import routes as project_routes
from app.core.config import get_settings
from app.core.database import execute, fetch_one, init_db
from app.schemas.api import ExportRequest
from app.services.behavioral_learning import init_behavioral_learning
from app.services.behavioral_triggers import init_behavioral_triggers
from app.services.forced_alignment import validate_forced_alignment_runtime
from app.services.semantic_ranker import probe_groq_readiness
from app.services.asr_providers import api_asr_runtime_snapshot, probe_api_asr_readiness
from app.services.jobs import (
    claim_next_job,
    init_job_queue,
    record_worker_heartbeat,
    release_claim,
    requeue_interrupted_worker_jobs,
    update_job,
)
from app.services.hinglish_stage1_routing import persisted_stage1_route
from app.services.storage_paths import confined_export_path


logger = logging.getLogger("clipkaro.worker")


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def _fail_reconstruction(job: dict, message: str, *, category: str | None = None) -> None:
    detail = message[:900]
    if job.get("project_id"):
        await execute(
            "UPDATE projects SET status='failed',stage='failed',error=?,updated_at=? WHERE id=?",
            (detail, project_routes.utcnow(), job["project_id"]),
        )
    if job.get("export_id"):
        # Export failure trigger releases only a still-reserved export slot.
        await execute(
            "UPDATE exports SET status='failed',error=? WHERE id=?",
            (detail, job["export_id"]),
        )
    if job.get("kind") == "cartoon_generate":
        cartoon_id = str((job.get("payload") or {}).get("cartoon_project_id") or "")
        if cartoon_id:
            await execute(
                "UPDATE cartoon_projects SET status='failed',stage='failed',error=?,updated_at=? WHERE id=?",
                (detail, project_routes.utcnow(), cartoon_id),
            )
    await update_job(job["id"], 0, "failed", detail, "failed", category or detail)


async def run_claimed_job(job: dict) -> None:
    """Reconstruct and execute one durable heavy job inside the worker container."""
    try:
        if job["kind"] in {"process_video", "upgrade_pipeline"}:
            project_id = str(job.get("project_id") or "")
            user = await fetch_one("SELECT * FROM users WHERE id=?", (job["user_id"],))
            video_id = str((job.get("payload") or {}).get("video_id") or "")
            video = None
            if video_id:
                video = await fetch_one("SELECT * FROM videos WHERE id=? AND project_id=?", (video_id, project_id))
            if not video:
                video = await fetch_one("SELECT * FROM videos WHERE project_id=?", (project_id,))
            if not user or not video:
                await _fail_reconstruction(job, "Project worker input no longer exists. Retry from the project page.")
                return
            route = persisted_stage1_route(job.get("payload"))
            force_transcribe = bool((job.get("payload") or {}).get("force_transcribe", False))
            await project_routes._process_project(
                job["id"], project_id, video["id"], user, route["asr_route"], force_transcribe,
            )
            return

        if job["kind"] == "cartoon_generate":
            from app.services.cartoon_job import run_cartoon_generation
            from app.services.storage import get_storage_provider

            with tempfile.TemporaryDirectory(prefix="clipkaro-cartoon-worker-") as directory:
                await run_cartoon_generation(job, Path(directory), get_storage_provider())
            return

        if job["kind"] == "render_export":
            export = await fetch_one("SELECT * FROM exports WHERE id=?", (job.get("export_id"),))
            request_payload = (job.get("payload") or {}).get("request")
            if not export or not isinstance(request_payload, dict):
                await _fail_reconstruction(job, "Export worker input is incomplete. Retry the export.")
                return
            try:
                request = ExportRequest(**request_payload)
            except Exception as exc:
                await _fail_reconstruction(job, f"Export request could not be restored: {type(exc).__name__}")
                return
            clip = await fetch_one(
                """SELECT c.*,p.user_id,p.id project_id FROM clips c
                   JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
                   WHERE c.id=? AND p.user_id=?""",
                (export["clip_id"], job["user_id"]),
            )
            video = await fetch_one("SELECT * FROM videos WHERE id=?", (clip["video_id"],)) if clip else None
            brand = None
            if request.brand_kit_id:
                brand = await fetch_one(
                    "SELECT * FROM brand_kits WHERE id=? AND user_id=?",
                    (request.brand_kit_id, job["user_id"]),
                )
            if not clip or not video:
                await _fail_reconstruction(job, "Export source no longer exists. Create a fresh export.")
                return
            output_path = confined_export_path(export.get("output_path"))
            if not output_path:
                await _fail_reconstruction(job, "Export output path is outside ClipKaro storage. Retry the export.")
                return
            await project_routes._render_export(
                job["id"], export["id"], clip, video, request,
                output_path, brand,
            )
            return

        await _fail_reconstruction(job, f"Unsupported worker job kind: {job['kind']}")
    finally:
        await release_claim(job["id"])


async def _recover_pre_worker_jobs() -> None:
    """Handle jobs that were already processing during the worker-isolation deploy.

    New isolated-worker jobs always carry a claim. A processing job with no claim
    therefore predates this worker process. Project jobs can be reconstructed;
    old render jobs cannot recover custom render parameters and fail/refund safely.
    """
    from app.core.database import fetch_all

    orphaned = await fetch_all(
        """SELECT j.* FROM jobs j LEFT JOIN job_claims c ON c.job_id=j.id
           WHERE j.status='processing' AND c.job_id IS NULL
             AND j.kind IN ('process_video','upgrade_pipeline','render_export','cartoon_generate')"""
    )
    for job in orphaned:
        if job["kind"] in {"process_video", "upgrade_pipeline", "cartoon_generate"}:
            await execute(
                "UPDATE jobs SET status='queued',stage='recovery',message='Migrated into isolated media worker',updated_at=? WHERE id=?",
                (project_routes.utcnow(), job["id"]),
            )
        else:
            payload = await fetch_one("SELECT payload_json FROM job_payloads WHERE job_id=?", (job["id"],))
            if payload and payload.get("payload_json") not in {None, "", "{}"}:
                await execute(
                    "UPDATE jobs SET status='queued',stage='recovery',message='Resuming in isolated media worker',updated_at=? WHERE id=?",
                    (project_routes.utcnow(), job["id"]),
                )
            else:
                await _fail_reconstruction(job, "A pre-isolation export was interrupted during deployment. Retry the export.")


def _worker_storage_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        target = path / f".worker-preflight-{uuid.uuid4().hex}"
        target.write_bytes(b"ok")
        target.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _whisper_capability() -> dict[str, object]:
    settings = get_settings()
    if settings.normalized_asr_mode == "api":
        return {"runtime_ready": True, "runtime_version": "api", "model_configured": True, "model_cache_writable": True}
    installed = importlib.util.find_spec("faster_whisper") is not None
    version = ""
    if installed:
        try:
            version = metadata.version("faster-whisper")
        except metadata.PackageNotFoundError:
            installed = False
    return {
        "runtime_ready": installed,
        "runtime_version": version,
        "model_configured": bool(settings.whisper_model.strip() and settings.whisper_secondary_model.strip()),
        "model_cache_writable": _worker_storage_writable(settings.model_cache_dir),
    }


def _hinglish_asr_capability(settings, provider_capability: dict[str, object]) -> dict[str, object]:
    """Secret-free Stage-1 provider readiness for API-side preflight.

    Provider credentials stay in the media worker. The API receives only this
    boolean/categorical capability through the durable worker heartbeat.
    """
    provider = settings.normalized_hinglish_asr_provider
    enabled = bool(settings.hinglish_roman_pipeline_enabled)
    if provider == "legacy":
        return {"provider": provider, "enabled": enabled, "ready": True, "fallback_ready": True}
    try:
        from app.services.hinglish_roman_pipeline import verify_frozen_policies
        policies_ready = bool(verify_frozen_policies())
    except Exception:
        policies_ready = False
    fallback_ready = (
        settings.normalized_asr_fallback_provider == "cloudflare"
        and str(provider_capability.get("fallback_status") or "") == "configured"
    )
    return {
        "provider": provider,
        "enabled": enabled,
        "ready": bool(settings.elevenlabs_keys) and policies_ready and fallback_ready,
        "fallback_ready": fallback_ready,
        "policies_ready": policies_ready,
    }


async def _worker_heartbeat_loop(
    worker_id: str,
    started_at: str,
    alignment_runtime: dict[str, object],
    whisper_capability: dict[str, object],
) -> None:
    settings = get_settings()
    heartbeat = max(1.0, float(settings.worker_heartbeat_seconds))
    provider_interval = max(30.0, float(settings.worker_provider_probe_seconds))
    provider: dict[str, object] = {"mode": settings.asr_mode, "code": "pending"}
    next_provider_probe = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            now = loop.time()
            if now >= next_provider_probe:
                provider = await api_asr_runtime_snapshot() if settings.normalized_asr_mode == "api" else await probe_groq_readiness()
                next_provider_probe = now + provider_interval
            alignment = {
                "ready": bool(alignment_runtime.get("enabled")) if settings.require_forced_alignment else True,
                "backend": str(alignment_runtime.get("backend") or settings.alignment_backend),
            }
            await record_worker_heartbeat(
                worker_id,
                status="ready",
                started_at=started_at,
                capabilities={
                    "whisper": whisper_capability,
                    "alignment": alignment,
                    "asr": provider,
                    "groq": provider,
                    "hinglish_asr": _hinglish_asr_capability(settings, provider),
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # A heartbeat write/probe failure must not crash an active media job;
            # missing/stale heartbeats make the API fail closed instead.
            logger.exception("Media-worker heartbeat update failed")
        await asyncio.sleep(heartbeat)


async def run_forever() -> None:
    settings = get_settings()
    if settings.job_execution_mode.strip().lower() != "worker":
        raise RuntimeError("The media worker requires JOB_EXECUTION_MODE=worker.")

    # Fail before opening the database or claiming any creator job.
    if settings.normalized_asr_mode == "api":
        readiness = await probe_api_asr_readiness()
        if not readiness["api_asr_ready"]:
            raise RuntimeError("API ASR mode requires Groq or configured Cloudflare fallback credentials.")
        if settings.hinglish_roman_pipeline_enabled and settings.normalized_hinglish_asr_provider == "elevenlabs":
            from app.services.hinglish_roman_pipeline import verify_frozen_policies
            if not settings.elevenlabs_keys or not verify_frozen_policies():
                raise RuntimeError("Enabled ElevenLabs Hinglish route requires ELEVENLABS_API_KEY and approved Roman V3/Display V1 policies.")
        alignment_runtime = {"enabled": False, "backend": "provider_native"}
        provider_capability = await api_asr_runtime_snapshot()
    else:
        alignment_runtime = validate_forced_alignment_runtime(settings.alignment_backend, settings.require_forced_alignment, enforce_production_policy=settings.app_env.strip().lower() == "production", enforce_pinned_versions=settings.app_env.strip().lower() == "production")
        provider_capability = {"enabled": settings.groq_ranking_enabled, "code": "pending"}
    logger.info("Alignment runtime validated: %s", alignment_runtime)

    await init_db()
    # The worker can be the first process to touch a fresh deployment database.
    # Install learning tables/triggers here too so export completion/failure is
    # captured even before the API container has finished starting.
    await init_behavioral_learning()
    await init_behavioral_triggers()
    await init_job_queue()
    from app.services.cartoon_repository import init_cartoon_studio
    await init_cartoon_studio()
    recovered = await requeue_interrupted_worker_jobs()
    await _recover_pre_worker_jobs()
    worker_id = _worker_id()
    started_at = project_routes.utcnow()
    # Write the first heartbeat synchronously so the API never sees a worker
    # container as healthy merely because Docker started its process.
    whisper_capability = _whisper_capability()
    await record_worker_heartbeat(
        worker_id,
        status="ready",
        started_at=started_at,
        capabilities={
            "whisper": whisper_capability,
            "alignment": {
                "ready": bool(alignment_runtime.get("enabled")) if settings.require_forced_alignment else True,
                "backend": str(alignment_runtime.get("backend") or settings.alignment_backend),
            },
            "asr": provider_capability,
            "groq": provider_capability,
            "hinglish_asr": _hinglish_asr_capability(settings, provider_capability),
        },
    )
    heartbeat_task = asyncio.create_task(
        _worker_heartbeat_loop(worker_id, started_at, alignment_runtime, whisper_capability)
    )
    logger.info("Isolated media worker started worker_id=%s recovered_claims=%s", worker_id, recovered)
    poll = max(0.1, float(settings.worker_poll_seconds))
    try:
        while True:
            job = await claim_next_job(worker_id)
            if not job:
                await asyncio.sleep(poll)
                continue
            try:
                await run_claimed_job(job)
            except asyncio.CancelledError:
                # Preserve the claim. The replacement worker requeues persisted
                # claims on startup, preventing two workers from running one job.
                raise
            except Exception as exc:
                logger.exception("Unhandled isolated worker failure job_id=%s", job.get("id"))
                message = str(getattr(exc, "public_message", "") or "The isolated media worker failed unexpectedly. Retry this job.")
                category = str(getattr(exc, "category", "") or "")
                try:
                    await _fail_reconstruction(job, message, category=category)
                finally:
                    await release_claim(job["id"])
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        try:
            await record_worker_heartbeat(
                worker_id, status="stopping", started_at=started_at,
                capabilities={"whisper": whisper_capability, "alignment": {"ready": False}, "groq": {"code": "stopping"}},
            )
        except Exception:
            logger.exception("Could not record media-worker shutdown heartbeat")


if __name__ == "__main__":
    asyncio.run(run_forever())

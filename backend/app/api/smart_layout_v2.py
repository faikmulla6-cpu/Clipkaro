"""Authenticated, feature-gated Smart Layout v2 analysis and private video.

Never accepts object keys or user IDs from the client. All media/analysis
operations bind to clip ownership via the existing session middleware.
The feature remains OFF until end-to-end media/preview QA is approved.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import get_settings
from app.core.database import distributed_advisory_lock, fetch_all, fetch_one
from app.services.auth import current_user
from app.services.distributed_rate_limit import consume_rate_limit
from app.services.jobs import create_job, dispatch_job, update_job
from app.services.smart_layout_cache import AnalysisIdentity, MODEL_VERSION, private_plan_key
from app.services.smart_layout_variants import all_variants_match_source
from app.services.storage import S3StorageProvider, get_storage_provider, validate_object_key
from app.services.storage_paths import confined_upload_path

router = APIRouter()
_MAX_JSON = 131072
_CHUNK = 64 * 1024
_MAX_RANGE = 4 * 1024 * 1024
_BYTE_RANGE = re.compile(r"^bytes=(\d+)-(\d*)$", re.ASCII)


def enabled() -> bool:
    return os.getenv("KARO_REAL_PREVIEW_ENABLED", "false").lower() == "true"


def _require_feature() -> None:
    if not enabled():
        raise HTTPException(404, "This preview is not available.")


async def _owned(clip_id: str, user_id: str) -> dict:
    row = await fetch_one(
        """SELECT c.id clip_id,c.start_time,c.end_time,c.status clip_status,
                  v.id video_id,v.file_path,v.object_generation,
                  v.original_filename,v.duration source_duration,
                  v.width source_width,v.height source_height,
                  v.status source_status,v.expires_at,p.id project_id
           FROM clips c JOIN videos v ON v.id=c.video_id
           JOIN projects p ON p.id=v.project_id
           WHERE c.id=? AND p.user_id=?""", (clip_id, user_id),
    )
    if not row:
        raise HTTPException(404, "Clip not found.")
    if row.get("clip_status") == "superseded":
        raise HTTPException(409, "This clip is no longer current.")
    if row.get("source_status") != "ready":
        raise HTTPException(410, "Original source is unavailable.")
    expires = str(row.get("expires_at") or "")
    if expires:
        try:
            if datetime.fromisoformat(expires.replace("Z","+00:00")).astimezone(timezone.utc) <= datetime.now(timezone.utc):
                raise HTTPException(410, "Original source has expired.")
        except ValueError:
            raise HTTPException(410, "Original source expiry cannot be verified.")
    return row


def _identity(row: dict, uid: str) -> AnalysisIdentity:
    try:
        return AnalysisIdentity(
            user_id=uid, project_id=row["project_id"],
            clip_id=row["clip_id"], video_id=row["video_id"],
            generation=str(row.get("object_generation") or ""),
            start=float(row["start_time"]), end=float(row["end_time"]),
        ).validated()
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, "The source version cannot be verified for analysis.") from exc


async def _cached(row: dict, identity: AnalysisIdentity) -> dict | None:
    key = private_plan_key(identity)
    storage = get_storage_provider()
    try:
        item = await asyncio.wait_for(storage.stat(key), timeout=12)
    except Exception as exc:
        raise HTTPException(503, "Private preview storage is temporarily unavailable.") from exc
    if item is None:
        return None
    if item.size < 100 or item.size > _MAX_JSON:
        return None  # Corrupt object: worker must replace it; never serve it.
    try:
        with tempfile.TemporaryDirectory(prefix="clipkaro-plan-") as tmp:
            destination = Path(tmp) / "plan.json"
            await asyncio.wait_for(storage.download(key, destination), timeout=15)
            if destination.stat().st_size > _MAX_JSON:
                raise ValueError("Unsafe cached plan size")
            cached = json.loads(destination.read_text(encoding="utf-8"))
        plans = cached.get("plans")
        if isinstance(plans, dict):
            from app.services.smart_layout_contract import validate_serialized_plan
            for item in plans.values():
                validate_serialized_plan(item)
        if (not isinstance(plans, dict) or cached.get("version") != 2
            or cached.get("model_version") != MODEL_VERSION
            or cached.get("cache_key") != key or not all_variants_match_source(plans)):
            raise ValueError("Invalid cached plan")
        if any(
            abs(float(p.get("source_start", -1)) - identity.start) > .01
            or abs(float(p.get("duration", -1)) - (identity.end - identity.start)) > .01
            or int(p.get("source_width", 0)) != int(row["source_width"])
            or int(p.get("source_height", 0)) != int(row["source_height"])
            for p in plans.values()
        ):
            raise ValueError("Plan does not belong to this source generation")
        return {"status": "ready", "plans": plans}
    except (asyncio.TimeoutError, OSError) as exc:
        raise HTTPException(503, "Private preview storage is temporarily unavailable.") from exc
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        # Fail closed, but permit the authorized worker to re-analyze and
        # atomically replace a stale or corrupt cache without changing B2 ACLs.
        import logging
        logging.getLogger("clipkaro.smartlayout.v2").warning(
            "Private Smart Layout cache invalid: %s", type(exc).__name__)
        return None


async def _active_job(clip_id: str, uid: str, key: str) -> dict | None:
    rows = await fetch_all(
        """SELECT j.id,j.status,j.created_at,p.payload_json FROM jobs j
           JOIN job_payloads p ON p.job_id=j.id
           WHERE j.user_id=? AND j.kind='smart_layout_analysis'
             AND j.status IN ('queued','processing')
           ORDER BY j.created_at DESC LIMIT 20""", (uid,),
    )
    for row in rows:
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except (TypeError, ValueError):
            continue
        if payload.get("clip_id") == clip_id and payload.get("cache_key") == key:
            return {"status": row["status"], "job_id": row["id"]}
    return None


@router.get("/clips/{clip_id}/smart-layout-v2")
async def analysis_status(clip_id: str, user: dict = Depends(current_user)) -> dict:
    _require_feature()
    row = await _owned(clip_id, str(user["id"]))
    identity = _identity(row, str(user["id"]))
    ready = await _cached(row, identity)
    if ready:
        return ready
    active = await _active_job(clip_id, str(user["id"]), private_plan_key(identity))
    return active or {"status": "not_started"}


@router.post("/clips/{clip_id}/smart-layout-v2", status_code=202)
async def request_analysis(
    clip_id: str, tasks: BackgroundTasks, user: dict = Depends(current_user),
) -> dict:
    _require_feature()
    uid = str(user["id"])
    row = await _owned(clip_id, uid)
    identity = _identity(row, uid)
    ready = await _cached(row, identity)
    if ready:
        return ready
    key = private_plan_key(identity)
    if not await consume_rate_limit(uid, group="smart_layout_preview", limit=8, window_seconds=86400):
        raise HTTPException(429, "Too many preview analysis requests today. Please retry later.")
    async with distributed_advisory_lock("smart-layout-v2:"+uid+":"+clip_id):
        cached = await _cached(row, identity)
        if cached:
            return cached
        existing = await _active_job(clip_id, uid, key)
        if existing:
            return existing
        pending = await fetch_one(
            """SELECT COUNT(*) n FROM jobs
               WHERE user_id=? AND kind='smart_layout_analysis'
                 AND status IN ('queued','processing')""", (uid,),
        )
        if int((pending or {}).get("n") or 0) >= 2:
            raise HTTPException(429, "Two previews are already being analyzed.")
        # Free preview compute is globally budgeted separately from billing.
        # A burst of analysis requests must not exhaust media-worker capacity.
        if not await consume_rate_limit(
            "global", group="smart_layout_preview_global", limit=80, window_seconds=3600
        ):
            raise HTTPException(429, "Smart Layout analysis is busy. Please try later.")
        job_id = await create_job(
            uid, "smart_layout_analysis",
            project_id=identity.project_id,
            payload={"clip_id": clip_id, "cache_key": key},
        )
    try:
        async def _local_worker(jid: str) -> None:
            from app.media_job import run_job
            await run_job(jid)
        await dispatch_job(tasks, _local_worker, job_id)
    except Exception as exc:
        await update_job(job_id, 0, "failed", "Could not start private preview", "failed", "PREVIEW_LAUNCH_FAILED")
        raise HTTPException(503, "Smart Layout analysis is temporarily unavailable.") from exc
    return {"status": "queued", "job_id": job_id}


@router.get("/clips/{clip_id}/smart-layout-v2/media")
async def original_canvas_video(
    clip_id: str, request: Request, user: dict = Depends(current_user),
):
    """Same-origin, authenticated, bounded HTTP Range proxy for private MP4.

    DO NOT redirect to B2: cross-origin signed video can taint browser Canvas.
    The request cannot supply a B2 key or access another user's source.
    """
    _require_feature()
    uid = str(user["id"])
    row = await _owned(clip_id, uid)
    if Path(str(row["original_filename"])).suffix.lower() != ".mp4":
        raise HTTPException(422, "This browser preview requires an MP4 source.")
    storage = get_storage_provider()
    if get_settings().normalized_storage_backend != "gcs":
        local = confined_upload_path(row.get("file_path"))
        if not local or not local.is_file():
            raise HTTPException(410, "Original source is unavailable.")
        return FileResponse(local, media_type="video/mp4", headers={"Cache-Control":"private, no-store"})
    if not isinstance(storage, S3StorageProvider):
        raise HTTPException(503, "Private preview media service is unavailable.")
    key = validate_object_key(
        str(row.get("file_path") or ""), expected_prefix=f"users/{uid}",
    )
    metadata = await storage.stat(key)
    if not metadata or metadata.size <= 0:
        raise HTTPException(410, "Original source is unavailable.")
    generation = str(row.get("object_generation") or "")
    if generation and metadata.generation != generation:
        raise HTTPException(409, "The source has changed; reload the editor.")
    size = metadata.size
    header = request.headers.get("range", "")
    match = _BYTE_RANGE.fullmatch(header) if header else None
    if header and not match:
        raise HTTPException(416, "Unsupported media range.")
    start = int(match.group(1)) if match else 0
    if start >= size:
        raise HTTPException(416, "Media range is outside the source.")
    requested_end = int(match.group(2)) if match and match.group(2) else size - 1
    if requested_end < start:
        raise HTTPException(416, "Invalid media range.")
    end = min(size-1, start+_MAX_RANGE-1, requested_end)
    if not await consume_rate_limit(uid, group="smart_layout_media", limit=360, window_seconds=3600):
        raise HTTPException(429, "Private preview download rate exceeded.")
    try:
        response = await asyncio.to_thread(
            storage.client.get_object, Bucket=storage.bucket, Key=key,
            Range=f"bytes={start}-{end}",
        )
    except Exception as exc:
        raise HTTPException(503, "Private preview media is temporarily unavailable.") from exc
    body = response["Body"]
    async def stream():
        try:
            remaining = end-start+1
            while remaining:
                chunk = await asyncio.to_thread(body.read, min(_CHUNK,remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            await asyncio.to_thread(body.close)
    return StreamingResponse(
        stream(), status_code=206, media_type="video/mp4",
        headers={
            "Accept-Ranges":"bytes",
            "Content-Range":f"bytes {start}-{end}/{size}",
            "Content-Length":str(end-start+1),
            "Cache-Control":"private, no-store",
            "X-Content-Type-Options":"nosniff",
        },
    )

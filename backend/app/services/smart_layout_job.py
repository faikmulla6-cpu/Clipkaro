"""Isolated media-worker task that caches owner-scoped Smart Layout analysis.

Never reads a user URL, creates an export, charges credits, or changes a
project's processing status. Only a previously owned Clipkaro source can enter
this pipeline. A single Auto Director face-analysis pass produces all modes.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.core.database import fetch_one
from app.services.jobs import update_job
from app.services.smart_layout_cache import AnalysisIdentity, MODEL_VERSION, private_plan_key
from app.services.smart_layout_variants import all_layout_variants, all_variants_match_source
from app.services.storage import S3StorageProvider, validate_object_key
from app.services.video import find_media_tool

MAX_LAYOUT_JSON_BYTES = 131072
MAX_SOURCE_BYTES = 2_500_000_000


async def _download_verified_source(storage, key: str, destination: Path,
                                    generation: str) -> None:
    """Pin the video bytes to the DB-confirmed B2 generation.

    A latest-object download is NOT enough: the source can be replaced while
    an analysis is queued. Stream to private scratch, never return signed URLs.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(storage, S3StorageProvider):
        def _copy() -> None:
            request = {"Bucket": storage.bucket, "Key": key}
            if generation.startswith("version:"):
                request["VersionId"] = generation.removeprefix("version:")
            elif generation.startswith("etag:"):
                request["IfMatch"] = '"' + generation.removeprefix("etag:") + '"'
            else:
                raise RuntimeError("Unverifiable source version")
            response = storage.client.get_object(**request)
            body = response["Body"]
            try:
                actual = (str(response.get("VersionId") or "") if generation.startswith("version:")
                          else str(response.get("ETag") or "").strip('"'))
                wanted = generation.split(":", 1)[1]
                if actual != wanted:
                    raise RuntimeError("Source version changed during analysis download")
                total = 0
                with destination.open("wb") as file:
                    while True:
                        chunk = body.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_SOURCE_BYTES:
                            raise RuntimeError("Smart Layout source exceeds processing limit")
                        file.write(chunk)
                if total < 1000:
                    raise RuntimeError("Source download was incomplete")
            finally:
                body.close()
        try:
            await asyncio.to_thread(_copy)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return

    current = await storage.stat(key)
    if not current or current.generation != generation or current.size > MAX_SOURCE_BYTES:
        raise RuntimeError("Source generation could not be verified")
    await storage.download(key, destination, generation=generation)
    after = await storage.stat(key)
    if not after or after.generation != generation or destination.stat().st_size != after.size:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Source changed during download")


ALLOWED_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi"})


async def run_smart_layout_analysis(job: dict, scratch: Path, storage) -> None:
    clip_id = str((job.get("payload") or {}).get("clip_id") or "")
    user_id = str(job.get("user_id") or "")
    if not clip_id or not user_id:
        raise RuntimeError("Smart Layout job is missing its trusted identity.")
    from app.api.smart_layout_v2 import _owned
    row = await fetch_one(
        """SELECT c.id clip_id,c.start_time,c.end_time,v.id video_id,
                  v.file_path,v.object_generation,v.original_filename,
                  v.duration source_duration,v.status source_status,
                  v.width source_width,v.height source_height,v.expires_at,p.id project_id
           FROM clips c JOIN videos v ON v.id=c.video_id
           JOIN projects p ON p.id=v.project_id
           WHERE c.id=? AND p.user_id=?""", (clip_id, user_id),
    )
    if not row or str(row["source_status"]) != "ready":
        raise RuntimeError("The authorized source is unavailable for Smart Layout.")
    # Enforce the identical ownership, source-expiry and superseded-clip policy
    # used by the public route, even for an already queued background job.
    await _owned(clip_id, user_id)
    start, end = float(row["start_time"]), float(row["end_time"])
    if start < 0 or end <= start or end > float(row["source_duration"]) + .1:
        raise RuntimeError("The clip range is invalid for the source.")
    identity = AnalysisIdentity(
        user_id=user_id, project_id=str(row["project_id"]),
        clip_id=clip_id, video_id=str(row["video_id"]),
        generation=str(row.get("object_generation") or ""),
        start=start, end=end,
    ).validated()
    key = private_plan_key(identity)
    expected_key = str((job.get("payload") or {}).get("cache_key") or "")
    if expected_key != key:
        # Request made before a source replacement/trim should never write a
        # new source's results under an earlier cache identity.
        raise RuntimeError("Smart Layout source version changed; please retry.")
    from app.api.smart_layout_v2 import _cached
    # Check existing cache via the same strict validator as the API. For an
    # invalid object, overwrite with a newly verified plan; never claim ready.
    if await _cached({"source_width": row["source_width"], "source_height": row["source_height"]}, identity):
        # A second request may finish while this job is still queued. Its
        # private verified result is reusable and must also finalize the
        # reservation exactly once, rather than leaving credits locked.
        from app.services.smart_layout_credits import settle_analysis_job
        await settle_analysis_job(str(job["id"]), succeeded=True)
        await update_job(job["id"], 100, "ready", "Smart Layout analysis cached", "completed")
        return

    source_key = validate_object_key(
        str(row.get("file_path") or ""), expected_prefix=f"users/{user_id}"
    )
    extension = Path(str(row.get("original_filename") or "")).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise RuntimeError("This video container cannot be analyzed for Smart Layout.")
    source = scratch / "uploads" / ("smart-source" + extension)
    await update_job(job["id"], 15, "downloading", "Preparing private source frames")
    await _download_verified_source(
        storage, source_key, source, str(row.get("object_generation") or "")
    )
    if not source.is_file() or source.stat().st_size < 1000:
        raise RuntimeError("The source is not readable.")
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Smart Layout analysis engine is unavailable.")
    from app.services.karo_smart_layouts import _detect
    await update_job(job["id"], 40, "analyzing", "Finding camera shots and visible faces")
    base = await asyncio.to_thread(_detect, source, start, end - start, ffmpeg, "auto")
    if base is None:
        raise RuntimeError("This footage cannot be analyzed reliably; Classic remains available.")
    if not any(
        scene.mode in {"dual_stack", "single", "speaker_focus"}
        or len(getattr(scene, "pair_centers", ())) == 2
        for scene in getattr(base, "segments", ())
    ):
        # Full-frame-only fallback is Classic, not a premium face analysis.
        # Fail before persisting/settling so the reserved credits are refunded.
        raise RuntimeError("No reliable live-person framing was found; Classic remains available.")
    plans = all_layout_variants(base, source_start=start, duration=end-start)
    if not all_variants_match_source(plans):
        raise RuntimeError("Smart Layout scene analysis is inconsistent.")

    record = {
        "version": 2, "model_version": MODEL_VERSION,
        "cache_key": key, "plans": plans,
    }
    encoded = json.dumps(
        record, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(encoded) > MAX_LAYOUT_JSON_BYTES:
        raise RuntimeError("Smart Layout analysis result exceeded safe limits.")
    await update_job(job["id"], 88, "saving", "Saving private reusable framing plan")
    from app.api.smart_layout_v2 import _identity
    fresh = await _owned(clip_id, user_id)
    if _identity(fresh, user_id) != identity:
        raise RuntimeError("The clip or source changed during Smart Layout analysis.")
    from app.services.smart_layout_repository import store_plan
    await store_plan(identity, record, source_expires_at=row.get("expires_at"))
    # Settlement follows verified private storage. A failed job is instead
    # released by update_job's isolated Smart Layout failure hook.
    from app.services.smart_layout_credits import settle_analysis_job
    await settle_analysis_job(str(job["id"]), succeeded=True)
    await update_job(job["id"], 100, "ready", "Smart Layout analysis ready", "completed")

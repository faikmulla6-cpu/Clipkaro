from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.services.storage import ObjectMetadata, validate_object_key
from app.services.youtube_import import YouTubeImportError, canonicalize_youtube_url


@dataclass(frozen=True)
class WorkerYouTubeSource:
    object_key: str
    metadata: ObjectMetadata
    video_id: str
    title: str
    duration: float
    size: int
    content_type: str = "video/mp4"


def _worker_endpoint(base_url: str) -> str:
    parsed = urlparse(str(base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise YouTubeImportError("YouTube ingestion worker is not configured safely. No Karo Minutes were charged.")
    return str(base_url).rstrip("/") + "/v1/ingest/youtube"


async def ingest_youtube_to_storage(
    url: str,
    *,
    user_id: str,
    project_id: str,
    max_minutes: float,
    remaining_minutes: float,
    max_bytes: int,
    storage,
    worker_url: str,
    worker_secret: str,
    timeout_seconds: float,
    upload_ttl_seconds: int,
) -> WorkerYouTubeSource:
    canonical, expected_id = canonicalize_youtube_url(url)
    if len(str(worker_secret or "")) < 32:
        raise YouTubeImportError("YouTube ingestion worker is not configured. No Karo Minutes were charged.")
    endpoint = _worker_endpoint(worker_url)
    object_key = validate_object_key(
        f"users/{user_id}/projects/{project_id}/source/{uuid.uuid4().hex}.mp4",
        expected_prefix=f"users/{user_id}/projects/{project_id}",
    )
    signed_url = await storage.signed_upload_url(
        object_key,
        content_type="video/mp4",
        ttl_seconds=max(120, min(int(upload_ttl_seconds), 3600)),
    )
    payload = {
        "url": canonical,
        "expected_video_id": expected_id,
        "upload_url": signed_url,
        "max_minutes": float(max_minutes),
        "remaining_minutes": float(remaining_minutes),
        "max_bytes": int(max_bytes),
    }
    timeout = httpx.Timeout(
        connect=min(15.0, float(timeout_seconds)),
        read=float(timeout_seconds),
        write=30.0,
        pool=15.0,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {worker_secret}"},
            )
    except (httpx.HTTPError, TimeoutError) as exc:
        await storage.delete(object_key)
        raise YouTubeImportError(
            "ClipKaro's YouTube ingestion worker is temporarily unavailable. No Karo Minutes were charged."
        ) from exc
    if response.status_code != 200:
        await storage.delete(object_key)
        if response.status_code in {401, 403}:
            message = "ClipKaro's YouTube ingestion worker is not authorized. No Karo Minutes were charged."
        elif response.status_code == 422:
            message = "This YouTube video does not fit the current plan limits or import requirements. No Karo Minutes were charged."
        else:
            message = "ClipKaro could not import this YouTube video right now. No Karo Minutes were charged."
        raise YouTubeImportError(message)
    try:
        data = response.json()
        video_id = str(data.get("video_id") or "")
        title = str(data.get("title") or "YouTube video").strip()[:120]
        duration = float(data.get("duration") or 0)
        size = int(data.get("size") or 0)
        content_type = str(data.get("content_type") or "").split(";", 1)[0].strip().lower()
    except (ValueError, TypeError, AttributeError) as exc:
        await storage.delete(object_key)
        raise YouTubeImportError("ClipKaro received an invalid ingestion-worker response. No Karo Minutes were charged.") from exc

    allowed_minutes = min(float(max_minutes), float(remaining_minutes))
    if (
        video_id != expected_id
        or duration <= 0
        or duration / 60.0 > allowed_minutes + 1e-6
        or size <= 0
        or size > int(max_bytes)
        or content_type != "video/mp4"
    ):
        await storage.delete(object_key)
        raise YouTubeImportError("ClipKaro rejected an invalid ingestion-worker result. No Karo Minutes were charged.")

    metadata = await storage.stat(object_key)
    if metadata is None or metadata.size != size or metadata.size <= 0:
        await storage.delete(object_key, generation=(metadata.generation if metadata else None))
        raise YouTubeImportError("Private storage could not verify the ingested YouTube source. No Karo Minutes were charged.")
    stored_type = str(metadata.content_type or "").split(";", 1)[0].strip().lower()
    if stored_type != "video/mp4":
        await storage.delete(object_key, generation=metadata.generation or None)
        raise YouTubeImportError("Private storage rejected the ingested YouTube source type. No Karo Minutes were charged.")

    return WorkerYouTubeSource(
        object_key=object_key,
        metadata=metadata,
        video_id=video_id,
        title=title or "YouTube video",
        duration=duration,
        size=size,
    )

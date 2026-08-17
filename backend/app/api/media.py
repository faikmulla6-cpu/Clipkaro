from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.database import fetch_one
from app.services.auth import current_user
from app.services.media_delivery import (
    MediaPreviewError,
    MediaToolUnavailable,
    ensure_browser_media,
    source_media_type,
)
from app.services.storage_paths import confined_upload_path


router = APIRouter()
logger = logging.getLogger("clipkaro.media")


async def _owned_video(project_id: str, user_id: str) -> dict:
    row = await fetch_one(
        """SELECT v.* FROM videos v JOIN projects p ON p.id=v.project_id
           WHERE p.id=? AND p.user_id=?""",
        (project_id, user_id),
    )
    if not row:
        raise HTTPException(404, "Video not found.")
    return row


@router.get("/projects/{project_id}/media/original")
async def project_original_media(project_id: str, user: dict = Depends(current_user)) -> FileResponse:
    """Serve the private uploaded bytes with their truthful container MIME.

    This route does not claim that every accepted source container/codec is
    playable by every browser; it exists for exact original-media delivery.
    """
    row = await _owned_video(project_id, str(user["id"]))
    source = confined_upload_path(row.get("file_path"))
    if source is None or not source.is_file():
        raise HTTPException(404, "Video not found or has expired.")
    media_type = source_media_type(row.get("original_filename"), source)
    return FileResponse(
        source,
        media_type=media_type,
        headers={
            "X-ClipKaro-Media-Mode": "original",
            "X-ClipKaro-Source-Media-Type": media_type,
        },
    )


@router.get("/projects/{project_id}/media")
async def project_browser_media(project_id: str, user: dict = Depends(current_user)) -> FileResponse:
    """Serve a browser-playable source preview without lying about MIME.

    H.264/AAC MP4 and compatible WebM can be delivered directly. Containers or
    codecs with inconsistent browser support are cached as an authenticated
    H.264/AAC MP4 proxy. Starlette FileResponse retains byte-range support for
    seeking in the project page and Creator Studio.
    """
    row = await _owned_video(project_id, str(user["id"]))
    source = confined_upload_path(row.get("file_path"))
    if source is None or not source.is_file():
        raise HTTPException(404, "Video not found or has expired.")
    source_type = source_media_type(row.get("original_filename"), source)
    safe_row = {**row, "file_path": str(source)}
    try:
        asset = await ensure_browser_media(safe_row)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Video not found or has expired.") from exc
    except MediaToolUnavailable as exc:
        logger.error(
            "Browser media engine unavailable project_id=%s video_id=%s error=%s",
            project_id,
            row.get("id"),
            exc,
        )
        raise HTTPException(503, "Browser preview is temporarily unavailable because the media engine is not ready.") from exc
    except MediaPreviewError as exc:
        logger.warning(
            "Browser preview normalization failed project_id=%s video_id=%s source_type=%s error=%s",
            project_id,
            row.get("id"),
            source_type,
            exc,
        )
        raise HTTPException(
            422,
            "This upload is valid enough to store, but ClipKaro could not prepare a browser-compatible preview. "
            "Try a standard H.264/AAC MP4 source.",
        ) from exc

    return FileResponse(
        asset.path,
        media_type=asset.media_type,
        headers={
            "X-ClipKaro-Media-Mode": asset.mode,
            "X-ClipKaro-Source-Media-Type": source_type,
        },
    )

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import execute, fetch_all
from app.services.media_delivery import remove_orphaned_previews, remove_preview_files
from app.services.storage_paths import confined_export_path, confined_upload_path
from app.core.config import get_settings
from app.services.storage import get_storage_provider, validate_object_key

logger = logging.getLogger("clipkaro.cleanup")


async def cleanup_expired() -> int:
    """Delete expired private media without letting one bad file stop retention.

    A row is marked ``expired`` only after its retained source/output has been
    successfully removed (or is already absent). Permission/storage failures
    remain eligible for the next sweep instead of falsely claiming deletion.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    from app.api.smart_layout_v2 import enabled as smart_layout_v2_enabled
    if smart_layout_v2_enabled():
        from app.services.smart_layout_repository import expire_old_plans
        await expire_old_plans()
    files = await fetch_all(
        "SELECT id,file_path FROM videos WHERE expires_at<? AND status<>'expired'",
        (timestamp,),
    )
    exports = await fetch_all(
        "SELECT id,output_path FROM exports WHERE expires_at<? AND status<>'expired'",
        (timestamp,),
    )
    removed = 0
    cloud = get_settings().normalized_storage_backend == "gcs"
    storage = get_storage_provider() if cloud else None
    upload_sessions = await fetch_all(
        """SELECT id,object_key FROM upload_sessions
           WHERE expires_at<? AND status IN ('initiated','rejected')""",
        (timestamp,),
    ) if cloud else []
    for item in files:
        try:
            if cloud:
                raw_key = str(item.get("file_path") or "")
                if raw_key.startswith("users/"):
                    key = validate_object_key(raw_key, expected_prefix="users/")
                elif raw_key.startswith("quarantine/"):
                    key = validate_object_key(raw_key, expected_prefix="quarantine/")
                else:
                    raise ValueError("Expired source is outside an authorized cloud retention namespace.")
                try:
                    deleted = int(await storage.delete(key))
                except Exception as exc:
                    # Only provider failures are isolated. DB errors still stop the sweep.
                    logger.error(
                        "Expired source cleanup will retry video_id=%s error_type=%s",
                        item.get("id"), type(exc).__name__,
                    )
                    continue
                removed += deleted
                await execute("UPDATE videos SET status='expired' WHERE id=?", (item["id"],))
                continue
            path = confined_upload_path(item.get("file_path"))
            if path is None:
                logger.error("Refused out-of-storage expired source deletion video_id=%s", item.get("id"))
                continue
            if path.exists():
                path.unlink()
                removed += 1
            removed += remove_preview_files(str(item["id"]))
            await execute("UPDATE videos SET status='expired' WHERE id=?", (item["id"],))
        except (OSError, ValueError) as exc:
            logger.error(
                "Expired source cleanup will retry video_id=%s error_type=%s",
                item.get("id"), type(exc).__name__,
            )

    for item in exports:
        try:
            if cloud:
                key = validate_object_key(str(item.get("output_path") or ""), expected_prefix="users/")
                try:
                    deleted = int(await storage.delete(key))
                except Exception as exc:
                    logger.error(
                        "Expired export cleanup will retry export_id=%s error_type=%s",
                        item.get("id"), type(exc).__name__,
                    )
                    continue
                removed += deleted
                await execute("UPDATE exports SET status='expired' WHERE id=?", (item["id"],))
                continue
            path = confined_export_path(item.get("output_path"))
            if path is None:
                logger.error("Refused out-of-storage expired export deletion export_id=%s", item.get("id"))
                continue
            if path.exists():
                path.unlink()
                removed += 1
            await execute("UPDATE exports SET status='expired' WHERE id=?", (item["id"],))
        except (OSError, ValueError) as exc:
            logger.error(
                "Expired export cleanup will retry export_id=%s error_type=%s",
                item.get("id"), type(exc).__name__,
            )

    for item in upload_sessions:
        try:
            key = validate_object_key(
                str(item.get("object_key") or ""), expected_prefix="quarantine/"
            )
            try:
                deleted = int(await storage.delete(key))
            except Exception as exc:
                logger.error(
                    "Expired upload-session cleanup will retry upload_session_id=%s error_type=%s",
                    item.get("id"), type(exc).__name__,
                )
                continue
            removed += deleted
            await execute(
                "UPDATE upload_sessions SET status='expired' WHERE id=? AND status IN ('initiated','rejected')",
                (item["id"],),
            )
        except (OSError, ValueError) as exc:
            logger.error(
                "Expired upload-session cleanup will retry upload_session_id=%s error_type=%s",
                item.get("id"), type(exc).__name__,
            )

    # A project can be manually deleted before its retention deadline. The DB
    # cascade removes the video row immediately, so sweep proxy files whose
    # owning video no longer exists rather than leaving private cache orphans.
    try:
        if cloud:
            return removed
        live_videos = await fetch_all("SELECT id FROM videos")
        removed += remove_orphaned_previews({str(item["id"]) for item in live_videos})
    except OSError as exc:
        logger.error("Orphan preview cleanup will retry error_type=%s", type(exc).__name__)
    return removed


async def cleanup_loop() -> None:
    while True:
        # Retention is background work, but a shutdown must not tear down the
        # event loop while an aiosqlite worker is still returning a DB result.
        # Shield the active sweep and, if shutdown arrives, let that sweep close
        # its connections cleanly before propagating cancellation.
        sweep = asyncio.create_task(cleanup_expired())
        try:
            await asyncio.shield(sweep)
        except asyncio.CancelledError:
            try:
                await sweep
            except Exception as exc:
                logger.error(
                    "Retention sweep failed during shutdown error_type=%s",
                    type(exc).__name__,
                )
            raise
        except Exception as exc:  # DB/runtime failures must not permanently kill retention.
            logger.error("Retention sweep failed and will retry error_type=%s", type(exc).__name__)
        await asyncio.sleep(3600)

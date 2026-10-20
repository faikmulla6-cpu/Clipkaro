"""Safe, bounded expiry cleanup for abandoned direct uploads.

Never mutate a consumed upload session: only uncompleted, expired staging
objects are eligible, so this cannot delete source media used by projects.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import execute, fetch_all, run_in_transaction
from app.services.storage import (
    cloud_object_storage_enabled, get_storage_provider, validate_object_key,
)

logger = logging.getLogger("clipkaro.upload_cleanup")


async def sweep_expired_uploads(*, limit: int = 100,
                                now: datetime | None = None) -> int:
    if not cloud_object_storage_enabled():
        return 0
    point = now or datetime.now(timezone.utc)
    # Allow extra time for requests that completed on the client near expiry.
    cutoff = (point - timedelta(minutes=15)).isoformat()
    rows = await fetch_all(
        """SELECT id,user_id,object_key,object_generation FROM upload_sessions
           WHERE status='initiated' AND expires_at<? ORDER BY expires_at LIMIT ?""",
        (cutoff, max(1, min(100, limit))),
    )
    storage = get_storage_provider()
    completed = 0
    for session in rows:
        try:
            async def claim(db) -> bool:
                cur = await db.execute(
                    """UPDATE upload_sessions SET status='expired'
                       WHERE id=? AND user_id=? AND status='initiated'
                       AND expires_at<? RETURNING id""",
                    (session["id"], session["user_id"], cutoff),
                )
                return await cur.fetchone() is not None

            # Claim before storage I/O. A concurrent successful completion
            # changes status to 'consumed' and cannot be deleted by this sweep.
            if not await run_in_transaction(
                claim, operation_name="claim expired upload for cleanup",
            ):
                continue
            key = validate_object_key(
                str(session["object_key"]),
                expected_prefix=f"quarantine/{session['user_id']}",
            )
            marker = str(session.get("object_generation") or "")
            if marker.startswith("multipart:"):
                try:
                    await storage.abort_multipart(key, marker[len("multipart:"):])
                except Exception as exc:
                    code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
                    if code not in {"NoSuchUpload", "404", "NotFound"}:
                        raise
            await storage.delete(key)
            # Keep the existing production-supported 'expired' terminal state.
            completed += 1
        except Exception:
            logger.exception("expired_private_upload_cleanup_failed session_id=%s", session["id"])
            # Safe retry on next sweep, without touching consumed sessions.
            try:
                await execute(
                    "UPDATE upload_sessions SET status='initiated' WHERE id=? AND status='expired'",
                    (session["id"],),
                )
            except Exception:
                logger.exception("failed_to_restore_expired_upload session_id=%s",session["id"])
    return completed

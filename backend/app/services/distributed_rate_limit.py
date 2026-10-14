from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.database import run_in_transaction


async def consume_rate_limit(identity: str, *, group: str, limit: int, window_seconds: int = 60) -> bool:
    """Return False when a PostgreSQL-authoritative fixed window is exhausted."""
    if get_settings().normalized_database_backend != "postgres":
        return True
    key = hashlib.sha256(f"{group}:{identity}".encode()).hexdigest()
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()

    async def consume(db) -> bool:
        # The persisted rate-limit timestamp columns use the legacy text shape,
        # while PostgreSQL infers explicit ?::timestamptz comparison parameters
        # as native timestamptz. Keep insert/update values as ISO text and pass
        # real datetime objects only to the explicitly cast comparison slots.
        cursor = await db.execute(
            """INSERT INTO security_rate_limits(bucket_key,window_started_at,request_count,updated_at)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(bucket_key) DO UPDATE SET
                 request_count=CASE
                   WHEN security_rate_limits.window_started_at::timestamptz <= (?::timestamptz - (? * interval '1 second')) THEN 1
                   ELSE security_rate_limits.request_count + 1 END,
                 window_started_at=CASE
                   WHEN security_rate_limits.window_started_at::timestamptz <= (?::timestamptz - (? * interval '1 second')) THEN EXCLUDED.window_started_at
                   ELSE security_rate_limits.window_started_at END,
                 updated_at=EXCLUDED.updated_at
               RETURNING request_count""",
            (key, now_text, now_text, now, window_seconds, now, window_seconds),
        )
        row = await cursor.fetchone()
        return bool(row and int(row["request_count"]) <= limit)

    return await run_in_transaction(consume, operation_name="distributed rate limit")

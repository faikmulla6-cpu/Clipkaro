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

    async def consume(db) -> bool:
        # asyncpg expects Python datetime objects for timestamptz parameters.
        # Passing ISO strings worked with SQLite but fails against PostgreSQL
        # before the SQL casts can run, so keep the values strongly typed here.
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
            (key, now, now, now, window_seconds, now, window_seconds),
        )
        row = await cursor.fetchone()
        return bool(row and int(row["request_count"]) <= limit)

    return await run_in_transaction(consume, operation_name="distributed rate limit")

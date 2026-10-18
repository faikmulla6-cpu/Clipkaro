"""Private, expiring, owner-scoped scene plans in Clipkaro's own database.

No B2 plan objects are ever created. Foreign-key cascades remove every plan
when its clip or project is deleted; the ordinary retention sweep deletes
expired plans. Face embeddings, private URLs and media bytes are NOT stored.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.database import execute, fetch_one
from app.services.smart_layout_cache import AnalysisIdentity, private_plan_key

MAX_PLAN_BYTES = 131072
CACHE_TTL = timedelta(days=14)


async def init_smart_layout_repository() -> None:
    await execute("""
       CREATE TABLE IF NOT EXISTS smart_layout_plans (
         cache_key TEXT PRIMARY KEY,
         user_id TEXT NOT NULL,
         project_id TEXT NOT NULL,
         clip_id TEXT NOT NULL,
         source_generation TEXT NOT NULL,
         plan_json TEXT NOT NULL,
         created_at TEXT NOT NULL,
         expires_at TEXT NOT NULL,
         FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
         FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
         FOREIGN KEY(clip_id) REFERENCES clips(id) ON DELETE CASCADE
       )
    """)
    await execute("CREATE INDEX IF NOT EXISTS idx_smart_layout_plans_expiry ON smart_layout_plans(expires_at)")
    await execute("CREATE INDEX IF NOT EXISTS idx_smart_layout_plans_owner ON smart_layout_plans(user_id,project_id)")


def _expiry(source_expires_at: str | None) -> str:
    now = datetime.now(timezone.utc)
    limit = now + CACHE_TTL
    if source_expires_at:
        source_end = datetime.fromisoformat(str(source_expires_at).replace("Z", "+00:00"))
        if source_end.tzinfo is None:
            source_end = source_end.replace(tzinfo=timezone.utc)
        limit = min(limit, source_end.astimezone(timezone.utc))
    if limit <= now:
        raise ValueError("Cannot retain Smart Layout for an expired source")
    return limit.isoformat()


async def read_plan(identity: AnalysisIdentity) -> dict[str, Any] | None:
    identity = identity.validated()
    item = await fetch_one(
        """SELECT plan_json,expires_at FROM smart_layout_plans
           WHERE cache_key=? AND user_id=? AND project_id=? AND clip_id=? AND source_generation=?""",
        (private_plan_key(identity),identity.user_id,identity.project_id,
         identity.clip_id,identity.generation),
    )
    if not item:
        return None
    expiry = datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00"))
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        return None
    raw = str(item["plan_json"])
    if len(raw.encode("utf-8")) > MAX_PLAN_BYTES:
        return None
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return decoded if isinstance(decoded, dict) else None


async def store_plan(identity: AnalysisIdentity, record: dict[str, Any],
                     *, source_expires_at: str | None) -> None:
    identity = identity.validated()
    encoded = json.dumps(record,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_PLAN_BYTES:
        raise ValueError("Private Smart Layout plan exceeds safe storage limits")
    expires_at = _expiry(source_expires_at)
    await execute(
        """INSERT INTO smart_layout_plans(
              cache_key,user_id,project_id,clip_id,source_generation,
              plan_json,created_at,expires_at
           ) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(cache_key) DO UPDATE SET
              plan_json=excluded.plan_json,created_at=excluded.created_at,
              expires_at=excluded.expires_at""",
        (private_plan_key(identity),identity.user_id,identity.project_id,
         identity.clip_id,identity.generation,encoded,
         datetime.now(timezone.utc).isoformat(),expires_at),
    )


async def expire_old_plans() -> None:
    """Called from Clipkaro's existing periodic media retention sweep."""
    await execute("DELETE FROM smart_layout_plans WHERE expires_at<=?",
                  (datetime.now(timezone.utc).isoformat(),))

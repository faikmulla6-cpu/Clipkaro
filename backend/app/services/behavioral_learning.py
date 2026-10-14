from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import Counter
from typing import Any

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.services.jobs import utcnow

logger = logging.getLogger("clipkaro.behavioral_learning")

CLIENT_EVENT_TYPES = {"impression", "preview_started", "selected", "edited"}
SERVER_EVENT_TYPES = {"export_requested", "export_ready", "export_failed", "downloaded"}
ALL_EVENT_TYPES = CLIENT_EVENT_TYPES | SERVER_EVENT_TYPES
ALLOWED_SURFACES = {"project", "editor", "export"}
ALLOWED_CHANGED_FIELDS = {"hook", "title", "transcript_text", "start_time", "end_time"}


async def init_behavioral_learning() -> None:
    """Install the append-only learning schema.

    Recommendation snapshots intentionally do not foreign-key `clip_id`: reprocessing
    deletes/replaces the current `clips` rows, but earlier generations must remain
    distinguishable until the creator deletes the project/account. Project/user FKs
    still enforce privacy deletion semantics.
    """
    if get_settings().normalized_database_backend == "postgres":
        return
    statements = [
        """
        CREATE TABLE IF NOT EXISTS recommendation_generations (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          project_id TEXT NOT NULL,
          video_id TEXT NOT NULL,
          language TEXT NOT NULL,
          category TEXT NOT NULL,
          ranking_source TEXT NOT NULL,
          ranking_model TEXT NOT NULL,
          app_version TEXT NOT NULL,
          pipeline_version TEXT NOT NULL,
          clip_count INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
          FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS clip_suggestion_snapshots (
          id TEXT PRIMARY KEY,
          generation_id TEXT NOT NULL,
          user_id TEXT NOT NULL,
          project_id TEXT NOT NULL,
          video_id TEXT NOT NULL,
          clip_id TEXT NOT NULL,
          suggestion_rank INTEGER NOT NULL CHECK(suggestion_rank > 0),
          start_time REAL NOT NULL,
          end_time REAL NOT NULL,
          duration REAL NOT NULL,
          score REAL NOT NULL,
          score_breakdown_json TEXT NOT NULL,
          platform TEXT NOT NULL,
          ranking_source TEXT NOT NULL,
          ranking_model TEXT NOT NULL,
          language TEXT NOT NULL,
          category TEXT NOT NULL,
          app_version TEXT NOT NULL,
          pipeline_version TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(generation_id) REFERENCES recommendation_generations(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
          FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
          UNIQUE(generation_id, clip_id),
          UNIQUE(generation_id, suggestion_rank)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS clip_behavior_events (
          id TEXT PRIMARY KEY,
          event_key TEXT UNIQUE NOT NULL,
          user_id TEXT NOT NULL,
          project_id TEXT NOT NULL,
          video_id TEXT NOT NULL,
          clip_id TEXT NOT NULL,
          generation_id TEXT NOT NULL,
          event_type TEXT NOT NULL CHECK(event_type IN (
            'impression','preview_started','selected','edited',
            'export_requested','export_ready','export_failed','downloaded'
          )),
          source TEXT NOT NULL CHECK(source IN ('frontend','server')),
          client_session_id TEXT,
          context_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
          FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
          FOREIGN KEY(generation_id) REFERENCES recommendation_generations(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_recommendation_generation_project ON recommendation_generations(project_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_suggestion_snapshot_clip ON clip_suggestion_snapshots(clip_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_behavior_user_created ON clip_behavior_events(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_behavior_generation_type ON clip_behavior_events(generation_id, event_type, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_behavior_clip_type ON clip_behavior_events(clip_id, event_type, created_at)",
    ]
    for statement in statements:
        await execute(statement)


async def _snapshot_for_clip(clip_id: str, user_id: str | None = None) -> dict | None:
    params: tuple[Any, ...] = (clip_id,)
    where = "s.clip_id=?"
    if user_id is not None:
        where += " AND s.user_id=?"
        params = (clip_id, user_id)
    return await fetch_one(
        f"""SELECT s.* FROM clip_suggestion_snapshots s
            WHERE {where} ORDER BY s.created_at DESC LIMIT 1""",
        params,
    )


def _client_context(surface: str, changed_fields: list[str] | None) -> dict[str, Any]:
    cleaned_surface = surface if surface in ALLOWED_SURFACES else "project"
    cleaned_fields = sorted({field for field in (changed_fields or []) if field in ALLOWED_CHANGED_FIELDS})
    payload: dict[str, Any] = {"surface": cleaned_surface}
    if cleaned_fields:
        payload["changed_fields"] = cleaned_fields
    return payload


def _digest_client_token(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


async def record_client_event(
    *,
    user_id: str,
    clip_id: str,
    event_type: str,
    client_event_id: str,
    client_session_id: str | None,
    surface: str,
    changed_fields: list[str] | None = None,
) -> dict[str, Any]:
    if event_type not in CLIENT_EVENT_TYPES:
        raise ValueError("Unsupported creator behavior event.")
    snapshot = await _snapshot_for_clip(clip_id, user_id)
    if not snapshot:
        raise LookupError("Clip suggestion not found.")
    event_digest = _digest_client_token(client_event_id)
    if not event_digest:
        raise ValueError("Behavior event ID is required.")
    event_key = f"client:{user_id}:{event_digest}"
    session_digest = _digest_client_token(client_session_id)
    context = _client_context(surface, changed_fields)
    await execute(
        """INSERT OR IGNORE INTO clip_behavior_events(
           id,event_key,user_id,project_id,video_id,clip_id,generation_id,event_type,source,
           client_session_id,context_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(uuid.uuid4()), event_key, user_id, snapshot["project_id"], snapshot["video_id"], clip_id,
            snapshot["generation_id"], event_type, "frontend", session_digest,
            json.dumps(context, separators=(",", ":"), sort_keys=True), utcnow(),
        ),
    )
    row = await fetch_one("SELECT id,event_type,created_at FROM clip_behavior_events WHERE event_key=?", (event_key,))
    return {"recorded": True, "event": row}


async def record_server_event(
    event_type: str,
    *,
    clip_id: str | None = None,
    export_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> bool:
    """Best-effort authoritative event recording; never breaks creator workflows."""
    if event_type not in SERVER_EVENT_TYPES:
        raise ValueError("Unsupported server behavior event.")
    try:
        resolved_clip = clip_id
        if not resolved_clip and export_id:
            export = await fetch_one("SELECT clip_id FROM exports WHERE id=?", (export_id,))
            resolved_clip = str(export["clip_id"]) if export else None
        if not resolved_clip:
            return False
        snapshot = await _snapshot_for_clip(resolved_clip)
        if not snapshot:
            return False
        resource = export_id or resolved_clip
        event_key = f"server:{event_type}:{resource}"[:240]
        safe_context: dict[str, Any] = {}
        if export_id:
            safe_context["export_id"] = export_id
        if context:
            for key in ("status", "resolution", "aspect_ratio", "caption_style"):
                if key in context and context[key] is not None:
                    safe_context[key] = str(context[key])[:80]
        await execute(
            """INSERT OR IGNORE INTO clip_behavior_events(
               id,event_key,user_id,project_id,video_id,clip_id,generation_id,event_type,source,
               client_session_id,context_json,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?)""",
            (
                str(uuid.uuid4()), event_key, snapshot["user_id"], snapshot["project_id"], snapshot["video_id"],
                resolved_clip, snapshot["generation_id"], event_type, "server",
                json.dumps(safe_context, separators=(",", ":"), sort_keys=True), utcnow(),
            ),
        )
        return True
    except Exception:
        logger.exception("Behavioral learning event failed event_type=%s export_id=%s clip_id=%s", event_type, export_id, clip_id)
        return False


async def learning_rows() -> list[dict[str, Any]]:
    """Return privacy-minimized offline rows. Unexposed suggestions are never negatives."""
    snapshots = await fetch_all(
        """SELECT id,generation_id,clip_id,suggestion_rank,duration,score,score_breakdown_json,
           platform,ranking_source,ranking_model,language,category,app_version,pipeline_version,created_at
           FROM clip_suggestion_snapshots ORDER BY created_at,suggestion_rank"""
    )
    event_rows = await fetch_all(
        "SELECT generation_id,clip_id,event_type,COUNT(*) count FROM clip_behavior_events GROUP BY generation_id,clip_id,event_type"
    )
    by_clip: dict[tuple[str, str], Counter[str]] = {}
    for row in event_rows:
        by_clip.setdefault((row["generation_id"], row["clip_id"]), Counter())[row["event_type"]] = int(row["count"])

    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        counts = by_clip.get((snapshot["generation_id"], snapshot["clip_id"]), Counter())
        if counts["downloaded"]:
            positive_strength: int | None = 5
        elif counts["export_ready"] or counts["export_requested"]:
            positive_strength = 4
        elif counts["edited"]:
            positive_strength = 3
        elif counts["selected"]:
            positive_strength = 2
        elif counts["preview_started"]:
            positive_strength = 1
        elif counts["impression"]:
            positive_strength = 0
        else:
            positive_strength = None
        provenance_ready = (
            str(snapshot.get("ranking_source") or "") not in {"", "pending"}
            and str(snapshot.get("ranking_model") or "") not in {"", "pending"}
        )
        observed = positive_strength is not None
        rows.append({
            "sample_id": snapshot["id"],
            "generation_id": snapshot["generation_id"],
            "suggestion_rank": snapshot["suggestion_rank"],
            "duration": snapshot["duration"],
            "score": snapshot["score"],
            "score_breakdown": json.loads(snapshot["score_breakdown_json"] or "{}"),
            "platform": snapshot["platform"],
            "ranking_source": snapshot["ranking_source"],
            "ranking_model": snapshot["ranking_model"],
            "language": snapshot["language"],
            "category": snapshot["category"],
            "app_version": snapshot["app_version"],
            "pipeline_version": snapshot["pipeline_version"],
            "events": {event: int(counts[event]) for event in sorted(ALL_EVENT_TYPES) if counts[event]},
            "label_strength": positive_strength,
            "eligible_negative": positive_strength == 0 and provenance_ready,
            "observed": observed,
            "provenance_ready": provenance_ready,
            "training_eligible": observed and provenance_ready,
        })
    return rows


async def learning_summary() -> dict[str, Any]:
    rows = await learning_rows()
    observed = [row for row in rows if row["observed"]]
    training_eligible = [row for row in rows if row["training_eligible"]]
    positives = [row for row in training_eligible if (row["label_strength"] or 0) > 0]
    exports = [row for row in training_eligible if (row["label_strength"] or 0) >= 4]
    return {
        "suggestions": len(rows),
        "observed_suggestions": len(observed),
        "coverage_rate": round(len(observed) / len(rows), 4) if rows else 0.0,
        "training_eligible": len(training_eligible),
        "provenance_pending": sum(1 for row in rows if not row["provenance_ready"]),
        "engaged_suggestions": len(positives),
        "export_intent_or_better": len(exports),
        "unexposed_not_negative": sum(1 for row in rows if not row["observed"]),
    }

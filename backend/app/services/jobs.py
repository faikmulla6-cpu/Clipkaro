import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one, run_in_transaction
from app.services.asr_gate import asr_queue_snapshot


HEAVY_JOB_KINDS = ("process_video", "upgrade_pipeline", "render_export")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_job_queue() -> None:
    """Install durable payload + claim tables without changing legacy jobs rows.

    Keeping payloads beside the existing jobs table avoids a risky positional
    jobs-schema migration while making every heavy operation reconstructable by
    a separate worker after an API/worker restart.
    """

    async def _migrate(db) -> None:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS job_payloads (
                 job_id TEXT PRIMARY KEY,
                 payload_json TEXT NOT NULL DEFAULT '{}',
                 created_at TEXT NOT NULL,
                 updated_at TEXT NOT NULL,
                 FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
               )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS job_claims (
                 job_id TEXT PRIMARY KEY,
                 worker_id TEXT NOT NULL,
                 claimed_at TEXT NOT NULL,
                 FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
               )"""
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_job_claims_worker ON job_claims(worker_id,claimed_at)")
        await db.execute(
            """CREATE TABLE IF NOT EXISTS worker_runtime_state (
                 id INTEGER PRIMARY KEY CHECK(id=1),
                 worker_id TEXT NOT NULL,
                 status TEXT NOT NULL,
                 started_at TEXT NOT NULL,
                 heartbeat_at TEXT NOT NULL,
                 capabilities_json TEXT NOT NULL DEFAULT '{}',
                 last_error_code TEXT NOT NULL DEFAULT ''
               )"""
        )

    await run_in_transaction(_migrate, operation_name="job queue schema migration")


async def record_worker_heartbeat(
    worker_id: str,
    *,
    status: str,
    started_at: str,
    capabilities: dict[str, Any],
    last_error_code: str = "",
) -> None:
    """Persist a single-worker liveness/capability snapshot without secrets."""
    timestamp = utcnow()
    payload = json.dumps(capabilities, separators=(",", ":"), ensure_ascii=False)
    await execute(
        """INSERT INTO worker_runtime_state(
             id,worker_id,status,started_at,heartbeat_at,capabilities_json,last_error_code
           ) VALUES (1,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             worker_id=excluded.worker_id,status=excluded.status,
             started_at=excluded.started_at,heartbeat_at=excluded.heartbeat_at,
             capabilities_json=excluded.capabilities_json,last_error_code=excluded.last_error_code""",
        (worker_id, status[:24], started_at, timestamp, payload, last_error_code[:80]),
    )


async def worker_runtime_snapshot() -> dict[str, Any] | None:
    """Return the durable worker snapshot for sanitized API-side readiness checks."""
    row = await fetch_one("SELECT * FROM worker_runtime_state WHERE id=1")
    if not row:
        return None
    snapshot = dict(row)
    try:
        capabilities = json.loads(str(snapshot.pop("capabilities_json", "{}") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        capabilities = {}
    snapshot["capabilities"] = capabilities if isinstance(capabilities, dict) else {}
    return snapshot


async def create_job(
    user_id: str,
    kind: str,
    project_id: str | None = None,
    export_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    job_id, timestamp = str(uuid.uuid4()), utcnow()
    serialized = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False)

    async def _create(db) -> None:
        await db.execute(
            """INSERT INTO jobs(
                 id,user_id,project_id,export_id,kind,status,progress,stage,message,error,created_at,updated_at
               ) VALUES (?, ?, ?, ?, ?, 'queued', 0, 'queued', 'Waiting to start', NULL, ?, ?)""",
            (job_id, user_id, project_id, export_id, kind, timestamp, timestamp),
        )
        await db.execute(
            "INSERT INTO job_payloads(job_id,payload_json,created_at,updated_at) VALUES (?,?,?,?)",
            (job_id, serialized, timestamp, timestamp),
        )

    await run_in_transaction(_create, operation_name="create durable job")
    return job_id


async def update_job(job_id: str, progress: int, stage: str, message: str, status: str = "processing", error: str | None = None) -> None:
    await execute("UPDATE jobs SET progress=?,stage=?,message=?,status=?,error=?,updated_at=? WHERE id=?",
                  (max(0, min(progress, 100)), stage, message, status, error, utcnow(), job_id))


def isolated_worker_enabled() -> bool:
    return get_settings().job_execution_mode.strip().lower() == "worker"


def dispatch_job(background_tasks: Any, function: Callable[..., Awaitable[Any]], *args: Any) -> None:
    """Run locally only outside isolated-worker production mode.

    In worker mode the durable jobs row is the dispatch mechanism. The API does
    not retain an in-memory coroutine that could execute Whisper/FFmpeg itself.
    """
    if not isolated_worker_enabled():
        background_tasks.add_task(function, *args)


async def claim_next_job(worker_id: str) -> dict[str, Any] | None:
    """Atomically claim the oldest queued heavy job for one isolated worker."""
    claimed_at = utcnow()

    async def _claim(db) -> dict[str, Any] | None:
        cursor = await db.execute(
            """SELECT j.*,COALESCE(p.payload_json,'{}') payload_json
               FROM jobs j LEFT JOIN job_payloads p ON p.job_id=j.id
               LEFT JOIN job_claims c ON c.job_id=j.id
               WHERE j.status='queued' AND c.job_id IS NULL
                 AND j.kind IN ('process_video','upgrade_pipeline','render_export')
               ORDER BY j.created_at ASC,j.id ASC LIMIT 1"""
        )
        row = await cursor.fetchone()
        if not row:
            return None
        job = dict(row)
        await db.execute(
            "INSERT INTO job_claims(job_id,worker_id,claimed_at) VALUES (?,?,?)",
            (job["id"], worker_id, claimed_at),
        )
        await db.execute(
            """UPDATE jobs SET status='processing',stage='claimed',message='Claimed by isolated media worker',updated_at=?
               WHERE id=? AND status='queued'""",
            (claimed_at, job["id"]),
        )
        job["status"] = "processing"
        job["payload"] = json.loads(job.pop("payload_json") or "{}")
        return job

    return await run_in_transaction(_claim, operation_name="claim isolated worker job")


async def release_claim(job_id: str) -> None:
    await execute("DELETE FROM job_claims WHERE job_id=?", (job_id,))


async def requeue_interrupted_worker_jobs() -> int:
    """Recover jobs whose only worker process/container was restarted.

    ClipKaro production intentionally runs one isolated media worker while using
    SQLite. On worker startup, any persisted claim therefore belongs to the dead
    predecessor and can be returned to the durable FIFO queue exactly once.
    """
    timestamp = utcnow()

    async def _requeue(db) -> int:
        cursor = await db.execute("SELECT COUNT(*) FROM job_claims")
        count = int((await cursor.fetchone())[0])
        await db.execute(
            """UPDATE jobs SET status='queued',stage='recovery',message='Resuming in isolated media worker',updated_at=?
               WHERE id IN (SELECT job_id FROM job_claims) AND status='processing'""",
            (timestamp,),
        )
        await db.execute("DELETE FROM job_claims")
        return count

    return await run_in_transaction(_requeue, operation_name="recover isolated worker claims")


async def _durable_worker_queue_snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("kind") not in HEAVY_JOB_KINDS:
        return None
    active_rows = await fetch_all(
        "SELECT id FROM jobs WHERE status='processing' AND kind IN ('process_video','upgrade_pipeline','render_export')"
    )
    active = len(active_rows)
    if row.get("status") == "queued":
        ahead = await fetch_all(
            """SELECT id FROM jobs
               WHERE status='queued' AND kind IN ('process_video','upgrade_pipeline','render_export')
                 AND (created_at < ? OR (created_at = ? AND id <= ?))""",
            (row["created_at"], row["created_at"], row["id"]),
        )
        queued = await fetch_all(
            "SELECT id FROM jobs WHERE status='queued' AND kind IN ('process_video','upgrade_pipeline','render_export')"
        )
        position = max(1, len(ahead))
        return {
            "asr_state": "queued",
            "queue_position": position,
            "queue_size": len(queued),
            "asr_active": active,
            "asr_limit": 1,
            "worker_state": "queued",
        }
    if row.get("status") == "processing":
        return {
            "asr_state": "running" if row.get("stage") == "transcribing" else "worker_running",
            "queue_position": 0,
            "queue_size": 0,
            "asr_active": active,
            "asr_limit": 1,
            "worker_state": "running",
        }
    return None


async def event_payload(job_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not row:
        return None
    payload = {k: row[k] for k in ("id", "kind", "status", "progress", "stage", "message", "error", "project_id", "export_id", "updated_at")}

    if isolated_worker_enabled():
        # API and media worker are separate processes, so process-local ASR gate
        # state is invisible to SSE. Derive queue position from the durable jobs
        # table instead; this remains truthful across restarts and API processes.
        queue = await _durable_worker_queue_snapshot(row)
        if queue:
            payload.update(queue)
            if row.get("status") == "queued":
                payload["message"] = f"Waiting safely for the media worker · queue position {queue['queue_position']}"
            elif row.get("stage") == "transcribing":
                payload["message"] = "Creating a timestamped transcript"
        return payload

    # Local/test background mode can expose the richer process-local ASR FIFO.
    if row.get("project_id") and row.get("stage") == "transcribing" and row.get("status") == "processing":
        video = await fetch_one("SELECT file_path FROM videos WHERE project_id=?", (row["project_id"],))
        if video and video.get("file_path"):
            queue = asr_queue_snapshot(video["file_path"])
            if queue:
                payload.update(queue)
                if queue["asr_state"] == "queued":
                    payload["message"] = f"Waiting safely for transcription · queue position {queue['queue_position']}"
                else:
                    payload["message"] = "Creating a timestamped transcript"
    return payload

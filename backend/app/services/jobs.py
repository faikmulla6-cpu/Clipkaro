import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one, run_in_transaction
from app.services.asr_gate import asr_queue_snapshot
from app.services.job_launcher import get_job_launcher


HEAVY_JOB_KINDS = ("process_video", "upgrade_pipeline", "render_export", "cartoon_generate")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_job_queue() -> None:
    """Install durable payload + claim tables without changing legacy jobs rows.

    Keeping payloads beside the existing jobs table avoids a risky positional
    jobs-schema migration while making every heavy operation reconstructable by
    a separate worker after an API/worker restart.
    """

    if get_settings().normalized_database_backend == "postgres":
        return  # Alembic owns production schema changes.

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
    timestamp = utcnow()
    if get_settings().normalized_database_backend == "postgres":
        await execute(
            """UPDATE jobs SET progress=?,stage=?,message=?,status=?,error=?,updated_at=?,
               heartbeat_at=?,completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END,
               failed_at=CASE WHEN ?='failed' THEN ? ELSE failed_at END WHERE id=?""",
            (max(0, min(progress, 100)), stage, message, status, error, timestamp, timestamp,
             status, timestamp, status, timestamp, job_id),
        )
    else:
        await execute("UPDATE jobs SET progress=?,stage=?,message=?,status=?,error=?,updated_at=? WHERE id=?",
                      (max(0, min(progress, 100)), stage, message, status, error, timestamp, job_id))
    if status == "failed":
        # Only the Smart Layout ledger is affected; existing media/export
        # reservations keep their independent trigger-driven settlement.
        kind = await fetch_one("SELECT kind FROM jobs WHERE id=?", (job_id,))
        if kind and kind.get("kind") == "smart_layout_analysis":
            from app.services.smart_layout_credits import settle_analysis_job
            await settle_analysis_job(job_id, succeeded=False)


def isolated_worker_enabled() -> bool:
    settings = get_settings()
    return settings.normalized_job_backend == "cloud_run_job" or settings.job_execution_mode.strip().lower() == "worker"


async def dispatch_job(background_tasks: Any, function: Callable[..., Awaitable[Any]], *args: Any) -> None:
    """Run locally only outside isolated-worker production mode.

    In worker mode the durable jobs row is the dispatch mechanism. The API does
    not retain an in-memory coroutine that could execute Whisper/FFmpeg itself.
    """
    settings = get_settings()
    if settings.normalized_job_backend == "cloud_run_job":
        job_id = str(args[0])
        await get_job_launcher().launch(job_id)
    elif not isolated_worker_enabled():
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
                 AND j.kind IN ('process_video','upgrade_pipeline','render_export','smart_layout_analysis','cartoon_generate')
               ORDER BY CASE WHEN j.kind='smart_layout_analysis' THEN 1 ELSE 0 END,
                        j.created_at ASC,j.id ASC LIMIT 1"""
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


async def claim_job(job_id: str, worker_id: str, *, execution_id: str = "") -> dict[str, Any] | None:
    """Atomically claim exactly one Cloud Run execution payload.

    A duplicate Cloud Run retry receives None and exits without charging or
    processing. PostgreSQL row locking is the production authority.
    """
    timestamp = utcnow()

    async def _claim(db) -> dict[str, Any] | None:
        # Lock only the real jobs row. PostgreSQL rejects FOR UPDATE against the
        # nullable side of the LEFT JOIN used for optional payloads.
        suffix = " FOR UPDATE OF j" if get_settings().normalized_database_backend == "postgres" else ""
        cursor = await db.execute(
            """SELECT j.*,COALESCE(p.payload_json,'{}') payload_json
               FROM jobs j LEFT JOIN job_payloads p ON p.job_id=j.id
               WHERE j.id=? AND j.status='queued'""" + suffix,
            (job_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        job = dict(row)
        if get_settings().normalized_database_backend == "postgres":
            await db.execute(
                """INSERT INTO job_claims(job_id,worker_id,claimed_at,heartbeat_at,attempt_count,cloud_run_execution)
                   VALUES (?,?,?,?,1,?) ON CONFLICT(job_id) DO NOTHING""",
                (job_id, worker_id, timestamp, timestamp, execution_id or None),
            )
            await db.execute(
                """UPDATE jobs SET status='processing',stage='claimed',message='Claimed by Cloud Run media job',
                   attempt_count=attempt_count+1,started_at=COALESCE(started_at,?),heartbeat_at=?,cloud_run_execution=?,updated_at=?
                   WHERE id=? AND status='queued'""",
                (timestamp, timestamp, execution_id or None, timestamp, job_id),
            )
        else:
            await db.execute("INSERT INTO job_claims(job_id,worker_id,claimed_at) VALUES (?,?,?)", (job_id, worker_id, timestamp))
            await db.execute("UPDATE jobs SET status='processing',stage='claimed',message='Claimed by media worker',updated_at=? WHERE id=? AND status='queued'", (timestamp, job_id))
        job["status"] = "processing"
        job["payload"] = json.loads(job.pop("payload_json") or "{}")
        return job

    return await run_in_transaction(_claim, operation_name="claim Cloud Run job")


async def heartbeat_job_claim(job_id: str) -> None:
    if get_settings().normalized_database_backend != "postgres":
        return
    timestamp = utcnow()
    await execute("UPDATE job_claims SET heartbeat_at=? WHERE job_id=?", (timestamp, job_id))
    await execute("UPDATE jobs SET heartbeat_at=?,updated_at=? WHERE id=? AND status='processing'", (timestamp, timestamp, job_id))


async def requeue_stale_jobs() -> int:
    """Reconcile dead Cloud Run executions without touching live claims."""
    if get_settings().normalized_database_backend != "postgres":
        return await requeue_interrupted_worker_jobs()
    seconds = max(60, int(get_settings().job_claim_stale_seconds))
    timestamp = utcnow()

    async def _requeue(db) -> int:
        cursor = await db.execute(
            """SELECT job_id FROM job_claims
               WHERE heartbeat_at::timestamptz < (CURRENT_TIMESTAMP - (? * interval '1 second')) FOR UPDATE""",
            (seconds,),
        )
        rows = await cursor.fetchall()
        ids = [row["job_id"] for row in rows]
        for stale_id in ids:
            await db.execute("DELETE FROM job_claims WHERE job_id=?", (stale_id,))
            await db.execute(
                """UPDATE jobs SET status='queued',stage='recovery',message='Recovered after stale Cloud Run execution',
                   heartbeat_at=NULL,updated_at=? WHERE id=? AND status='processing'""",
                (timestamp, stale_id),
            )
        return len(ids)

    return await run_in_transaction(_requeue, operation_name="reconcile stale Cloud Run jobs")


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
        "SELECT id FROM jobs WHERE status='processing' AND kind IN ('process_video','upgrade_pipeline','render_export','cartoon_generate')"
    )
    active = len(active_rows)
    if row.get("status") == "queued":
        ahead = await fetch_all(
            """SELECT id FROM jobs
               WHERE status='queued' AND kind IN ('process_video','upgrade_pipeline','render_export','cartoon_generate')
                 AND (created_at < ? OR (created_at = ? AND id <= ?))""",
            (row["created_at"], row["created_at"], row["id"]),
        )
        queued = await fetch_all(
            "SELECT id FROM jobs WHERE status='queued' AND kind IN ('process_video','upgrade_pipeline','render_export','cartoon_generate')"
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

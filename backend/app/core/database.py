from __future__ import annotations

import asyncio
import logging
import sqlite3
import re
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

import aiosqlite

try:  # Local SQLite development must not require PostgreSQL client loading.
    import asyncpg
except ImportError:  # pragma: no cover - exercised by minimal local installs.
    asyncpg = None

from .config import get_settings


T = TypeVar("T")
logger = logging.getLogger("clipkaro.database")
_LOCK_MESSAGES = ("database is locked", "database table is locked", "database schema is locked")
_LOCK_PRIMARY_CODES = {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
POSTGRES_SCHEMA_REVISION = "20261122_15"
POSTGRES_PREVIOUS_SCHEMA_REVISION = "20261121_14"
_postgres_pool: Any = None


class _PostgresCursor:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    async def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[Any]:
        return list(self._rows)


def _postgres_query(query: str) -> str:
    """Translate the small legacy helper dialect without touching literals.

    This is intentionally bounded. SQLite-only schema/trigger SQL is never sent
    through this path; PostgreSQL schema changes are owned by Alembic.
    """
    sql = query.strip()
    upper = sql.upper()
    if upper.startswith("PRAGMA "):
        raise RuntimeError("SQLite PRAGMA is not valid in PostgreSQL mode.")
    if upper.startswith("INSERT OR IGNORE "):
        sql = re.sub(r"^INSERT\s+OR\s+IGNORE", "INSERT", sql, flags=re.IGNORECASE)
        sql = f"{sql} ON CONFLICT DO NOTHING"
    elif upper.startswith("INSERT OR REPLACE INTO BILLING_PLANS"):
        sql = re.sub(r"^INSERT\s+OR\s+REPLACE", "INSERT", sql, flags=re.IGNORECASE)
        sql += " ON CONFLICT(plan_key) DO UPDATE SET provider_plan_id=EXCLUDED.provider_plan_id, amount=EXCLUDED.amount, currency=EXCLUDED.currency, created_at=EXCLUDED.created_at"
    sql = sql.replace("MAX(source_minutes,?)", "GREATEST(source_minutes,?)")
    sql = sql.replace("MAX(exports_used,?)", "GREATEST(exports_used,?)")
    sql = sql.replace("MAX(billing_webhook_state.last_event_created_at,excluded.last_event_created_at)", "GREATEST(billing_webhook_state.last_event_created_at,excluded.last_event_created_at)")
    sql = sql.replace("MAX(billing_webhook_state.terminal,excluded.terminal)", "GREATEST(billing_webhook_state.terminal,excluded.terminal)")
    index = 0
    quoted = False
    output: list[str] = []
    position = 0
    while position < len(sql):
        char = sql[position]
        if char == "'":
            output.append(char)
            if quoted and position + 1 < len(sql) and sql[position + 1] == "'":
                output.append("'")
                position += 2
                continue
            quoted = not quoted
        elif char == "?" and not quoted:
            index += 1
            output.append(f"${index}")
        else:
            output.append(char)
        position += 1
    return "".join(output)


class _PostgresConnection:
    def __init__(self, connection: Any) -> None:
        self.raw = connection

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> _PostgresCursor:
        sql = _postgres_query(query)
        if sql.lstrip().upper().startswith(("SELECT", "WITH")) or " RETURNING " in sql.upper():
            return _PostgresCursor(list(await self.raw.fetch(sql, *params)))
        await self.raw.execute(sql, *params)
        return _PostgresCursor()

    async def executemany(self, query: str, rows: Iterable[tuple[Any, ...]]) -> None:
        await self.raw.executemany(_postgres_query(query), list(rows))


async def _get_postgres_pool() -> Any:
    global _postgres_pool
    if _postgres_pool is not None:
        return _postgres_pool
    settings = get_settings()
    if asyncpg is None:
        raise RuntimeError("PostgreSQL mode requires the asyncpg package.")
    if not settings.database_url.strip():
        raise RuntimeError("DATABASE_URL is required for PostgreSQL mode.")
    _postgres_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=max(0, int(settings.postgres_pool_min_size)),
        max_size=max(1, int(settings.postgres_pool_max_size)),
        command_timeout=max(1.0, float(settings.postgres_command_timeout_seconds)),
        statement_cache_size=max(0, int(settings.postgres_statement_cache_size)),
        server_settings={"application_name": "clipkaro"},
    )
    return _postgres_pool


async def close_database() -> None:
    global _postgres_pool
    if _postgres_pool is not None:
        await _postgres_pool.close()
        _postgres_pool = None


@asynccontextmanager
async def distributed_advisory_lock(key: str):
    """Serialize a sensitive cross-instance operation in PostgreSQL mode."""
    if get_settings().normalized_database_backend != "postgres":
        yield
        return
    pool = await _get_postgres_pool()
    async with pool.acquire() as connection:
        await connection.execute("SELECT pg_advisory_lock(hashtextextended($1, 0))", key)
        try:
            yield
        finally:
            await connection.execute("SELECT pg_advisory_unlock(hashtextextended($1, 0))", key)


class UsageQuotaExceeded(RuntimeError):
    """Raised when an atomic Karo Minute or Short reservation cannot be created."""


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, plan TEXT NOT NULL DEFAULT 'free', role TEXT NOT NULL DEFAULT 'creator',
  onboarding_complete INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  billing_reference TEXT, plan_started_at TEXT, plan_expires_at TEXT,
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
  post_karo_access_override INTEGER NOT NULL DEFAULT 0,
  cartoon_studio_access_override INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT '',
  status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'created',
  language TEXT DEFAULT 'auto', category TEXT DEFAULT 'auto', error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, original_filename TEXT NOT NULL,
  duration REAL DEFAULT 0, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
  file_size INTEGER DEFAULT 0, file_path TEXT NOT NULL, status TEXT NOT NULL,
  object_generation TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS transcripts (
  id TEXT PRIMARY KEY, video_id TEXT NOT NULL, language TEXT NOT NULL,
  text TEXT NOT NULL, segments_json TEXT NOT NULL, created_at TEXT NOT NULL,
  FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS transcript_corrections (
  id TEXT PRIMARY KEY, transcript_id TEXT NOT NULL, project_id TEXT NOT NULL, video_id TEXT NOT NULL,
  segment_index INTEGER NOT NULL, segment_key TEXT NOT NULL, original_text TEXT NOT NULL,
  corrected_text TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'corrected',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(transcript_id, segment_key),
  FOREIGN KEY(transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS clips (
  id TEXT PRIMARY KEY, video_id TEXT NOT NULL, start_time REAL NOT NULL, end_time REAL NOT NULL,
  hook TEXT NOT NULL, title TEXT NOT NULL, reason TEXT NOT NULL, transcript_text TEXT DEFAULT '',
  score REAL NOT NULL, score_breakdown_json TEXT NOT NULL DEFAULT '{}', platform TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS clip_edit_plans (
  clip_id TEXT PRIMARY KEY, plan_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL,
  FOREIGN KEY(clip_id) REFERENCES clips(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS exports (
  id TEXT PRIMARY KEY, clip_id TEXT NOT NULL, user_id TEXT NOT NULL, output_path TEXT NOT NULL,
  resolution TEXT NOT NULL, aspect_ratio TEXT NOT NULL DEFAULT '9:16', caption_style TEXT NOT NULL,
  watermark INTEGER NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
  error TEXT, object_generation TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  FOREIGN KEY(clip_id) REFERENCES clips(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, export_id TEXT,
  kind TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
  stage TEXT NOT NULL, message TEXT NOT NULL, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS usage (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, month TEXT NOT NULL,
  source_minutes REAL NOT NULL DEFAULT 0, exports_used INTEGER NOT NULL DEFAULT 0,
  exports_limit INTEGER NOT NULL, UNIQUE(user_id, month),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS usage_reservations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, period_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('minutes','export')),
  amount REAL NOT NULL CHECK(amount > 0), resource_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('reserved','finalized','released')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS brand_kits (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, primary_color TEXT NOT NULL,
  accent_color TEXT NOT NULL, font_family TEXT NOT NULL, logo_text TEXT DEFAULT '',
  caption_preset TEXT NOT NULL DEFAULT 'kinetic', is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS scheduled_posts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, export_id TEXT NOT NULL, platform TEXT NOT NULL,
  caption TEXT NOT NULL, hashtags TEXT NOT NULL DEFAULT '', scheduled_for TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(export_id) REFERENCES exports(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS content_packs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}', provider TEXT DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS post_karo_connections (
  user_id TEXT PRIMARY KEY, api_key_ciphertext TEXT NOT NULL, api_key_masked TEXT NOT NULL,
  api_key_fingerprint TEXT NOT NULL, profile_id TEXT NOT NULL, validated_at TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS post_karo_accounts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, platform TEXT NOT NULL CHECK(platform IN ('instagram','youtube')),
  provider_account_id TEXT NOT NULL, username TEXT NOT NULL DEFAULT '', display_name TEXT NOT NULL DEFAULT '',
  can_post INTEGER NOT NULL DEFAULT 1, connection_status TEXT NOT NULL DEFAULT 'connected',
  health_json TEXT NOT NULL DEFAULT '{}', last_synced_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id,platform), UNIQUE(user_id,provider_account_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS post_karo_drafts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, export_id TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
  instagram_enabled INTEGER NOT NULL DEFAULT 0, instagram_caption TEXT NOT NULL DEFAULT '',
  instagram_hashtags TEXT NOT NULL DEFAULT '[]', youtube_enabled INTEGER NOT NULL DEFAULT 0,
  youtube_title TEXT NOT NULL DEFAULT '', youtube_description TEXT NOT NULL DEFAULT '',
  youtube_tags TEXT NOT NULL DEFAULT '[]', youtube_visibility TEXT NOT NULL DEFAULT 'public'
    CHECK(youtube_visibility IN ('public','unlisted','private')),
  scheduled_for TEXT, timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id,export_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(export_id) REFERENCES exports(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS post_karo_publications (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, export_id TEXT NOT NULL, draft_id TEXT NOT NULL,
  draft_revision INTEGER NOT NULL CHECK(draft_revision > 0), request_id TEXT NOT NULL, job_id TEXT,
  mode TEXT NOT NULL CHECK(mode IN ('now','schedule')), status TEXT NOT NULL
    CHECK(status IN ('queued','processing','scheduled','published','partial','failed')),
  snapshot_json TEXT NOT NULL, provider_post_id TEXT, platform_results_json TEXT NOT NULL DEFAULT '[]',
  error TEXT, scheduled_for TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id,request_id), UNIQUE(draft_id,draft_revision),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(export_id) REFERENCES exports(id) ON DELETE CASCADE,
  FOREIGN KEY(draft_id) REFERENCES post_karo_drafts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, user_id TEXT, event TEXT NOT NULL, entity_type TEXT, entity_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_events (
  id TEXT PRIMARY KEY, provider_event_id TEXT UNIQUE NOT NULL, user_id TEXT,
  event_type TEXT NOT NULL, plan TEXT, amount INTEGER DEFAULT 0,
  status TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_plans (
  plan_key TEXT PRIMARY KEY, provider_plan_id TEXT UNIQUE NOT NULL, amount INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'INR', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS short_credit_reservations (
  clip_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, period_key TEXT NOT NULL,
  export_id TEXT NOT NULL, status TEXT NOT NULL
    CHECK(status IN ('reserved','finalized','released')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_short_credit_period
  ON short_credit_reservations(user_id,period_key,status);
CREATE TABLE IF NOT EXISTS billing_plan_versions (
  provider_plan_id TEXT PRIMARY KEY, plan_key TEXT NOT NULL, amount INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'INR', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS legacy_billing_subscriptions (
  subscription_id TEXT PRIMARY KEY, plan_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_entitlement_snapshots (
  user_id TEXT NOT NULL, period_key TEXT NOT NULL, plan_key TEXT NOT NULL,
  processing_minutes REAL NOT NULL CHECK(processing_minutes>0),
  shorts INTEGER NOT NULL CHECK(shorts>0),
  source_video_limit_minutes REAL NOT NULL CHECK(source_video_limit_minutes>0),
  short_mode TEXT NOT NULL CHECK(short_mode IN ('source_projects','finished_shorts')),
  price_paise INTEGER NOT NULL CHECK(price_paise>=0), created_at TEXT NOT NULL,
  PRIMARY KEY(user_id,period_key), FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS billing_checkouts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, plan TEXT NOT NULL,
  provider_reference TEXT UNIQUE NOT NULL, amount INTEGER NOT NULL, status TEXT NOT NULL,
  payment_id TEXT, created_at TEXT NOT NULL, verified_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
-- Paid top-ups are independent from plan snapshots and survive billing periods.
CREATE TABLE IF NOT EXISTS credit_topup_wallets (
  user_id TEXT PRIMARY KEY, minutes_balance REAL NOT NULL DEFAULT 0 CHECK(minutes_balance>=-0.000001),
  shorts_balance INTEGER NOT NULL DEFAULT 0 CHECK(shorts_balance>=0), updated_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS credit_topup_checkouts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, provider_reference TEXT UNIQUE NOT NULL,
  minutes INTEGER NOT NULL CHECK(minutes>=0),shorts INTEGER NOT NULL CHECK(shorts>=0),
  amount_paise INTEGER NOT NULL CHECK(amount_paise>0), status TEXT NOT NULL,
  payment_id TEXT,created_at TEXT NOT NULL,verified_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS credit_topup_spends (
  user_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('minutes','shorts')),
  resource_id TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0),
  status TEXT NOT NULL CHECK(status IN ('reserved','finalized','released')),
  created_at TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(kind,resource_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_credit_topup_checkouts_user ON credit_topup_checkouts(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_topup_spends_user ON credit_topup_spends(user_id,status);
CREATE TABLE IF NOT EXISTS checkout_entitlement_snapshots (
  checkout_id TEXT PRIMARY KEY, processing_minutes REAL NOT NULL,
  shorts INTEGER NOT NULL, source_video_limit_minutes REAL NOT NULL,
  short_mode TEXT NOT NULL CHECK(short_mode IN ('source_projects','finished_shorts')),
  price_paise INTEGER NOT NULL, created_at TEXT NOT NULL,
  FOREIGN KEY(checkout_id) REFERENCES billing_checkouts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_project ON videos(project_id);
CREATE INDEX IF NOT EXISTS idx_transcript_corrections_project ON transcript_corrections(project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_clips_video ON clips(video_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_exports_user ON exports(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_reservation_period ON usage_reservations(user_id, period_key, kind, status);
CREATE INDEX IF NOT EXISTS idx_usage_reservation_resource ON usage_reservations(kind, resource_id, status);
CREATE INDEX IF NOT EXISTS idx_content_packs_project ON content_packs(project_id);
CREATE INDEX IF NOT EXISTS idx_post_karo_accounts_user ON post_karo_accounts(user_id,platform);
CREATE INDEX IF NOT EXISTS idx_post_karo_publications_user ON post_karo_publications(user_id,created_at DESC);

-- A video's duration is known at the validated transition. Reserve its Karo
-- Minutes and one AI Short creation in the same SQLite write transaction before transcription starts.
DROP TRIGGER IF EXISTS trg_reserve_video_minutes;
CREATE TRIGGER trg_reserve_video_minutes
BEFORE UPDATE OF status ON videos
WHEN NEW.status = 'validated'
 AND NEW.duration > 0
 AND NOT EXISTS (
   SELECT 1 FROM usage_reservations
   WHERE kind='minutes' AND resource_id=NEW.project_id AND status IN ('reserved','finalized')
 )
BEGIN
  INSERT OR IGNORE INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
  SELECT lower(hex(randomblob(16))), p.user_id,
    CASE WHEN u.plan='free'
      THEN 'free:' || strftime('%Y-%m','now')
      ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
           substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
    END,
    0, 0,
    CASE u.plan
      WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50
      WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END
  FROM projects p JOIN users u ON u.id=p.user_id WHERE p.id=NEW.project_id;

  UPDATE usage SET exports_limit=(
    SELECT CASE u.plan
      WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50
      WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END
    FROM projects p JOIN users u ON u.id=p.user_id WHERE p.id=NEW.project_id
  )
  WHERE user_id=(SELECT user_id FROM projects WHERE id=NEW.project_id)
    AND month=(
      SELECT CASE WHEN u.plan='free'
        THEN 'free:' || strftime('%Y-%m','now')
        ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
             substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
      END
      FROM projects p JOIN users u ON u.id=p.user_id WHERE p.id=NEW.project_id
    );

  SELECT CASE WHEN EXISTS(
    SELECT 1 FROM projects p JOIN users u ON u.id=p.user_id
    LEFT JOIN plan_entitlement_snapshots s ON s.user_id=u.id
      AND s.period_key=(CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now')
        ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local')
             || ':' || substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END)
    WHERE p.id=NEW.project_id
      AND COALESCE(s.short_mode,'source_projects')='source_projects'
      AND (SELECT COUNT(DISTINCT r.resource_id) FROM usage_reservations r
           WHERE r.user_id=u.id AND r.kind='minutes'
             AND r.status IN ('reserved','finalized')
             AND r.period_key=(CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now')
               ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local')
                    || ':' || substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END))
           >= COALESCE(s.shorts,CASE u.plan
            WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50
            WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END)
      AND (u.plan NOT IN ('creator','growth','pro','agency') OR
           COALESCE((SELECT w.shorts_balance FROM credit_topup_wallets w WHERE w.user_id=u.id),0)<=0)
  ) THEN RAISE(ABORT,'AI_SHORT_QUOTA_EXCEEDED') END;

  UPDATE credit_topup_wallets SET shorts_balance=shorts_balance-1,
    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND EXISTS(SELECT 1 FROM users u LEFT JOIN plan_entitlement_snapshots s ON s.user_id=u.id
  AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))
  WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND COALESCE(s.short_mode,'source_projects')='source_projects'
  AND (SELECT COUNT(DISTINCT r.resource_id) FROM usage_reservations r
       WHERE r.user_id=u.id AND r.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)) AND r.kind='minutes'
         AND r.status IN ('reserved','finalized'))>=COALESCE(s.shorts,CASE u.plan
       WHEN 'creator' THEN 15 WHEN 'growth' THEN 50 WHEN 'pro' THEN 150
       WHEN 'mini_pass' THEN 5 WHEN 'agency' THEN 500 ELSE 2 END));
  INSERT INTO credit_topup_spends(user_id,kind,resource_id,amount,status,created_at,updated_at)
    SELECT (SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id),'shorts',NEW.project_id,1,'reserved',
      strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE EXISTS(SELECT 1 FROM users u LEFT JOIN plan_entitlement_snapshots s ON s.user_id=u.id
  AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))
  WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND COALESCE(s.short_mode,'source_projects')='source_projects'
  AND (SELECT COUNT(DISTINCT r.resource_id) FROM usage_reservations r
       WHERE r.user_id=u.id AND r.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)) AND r.kind='minutes'
         AND r.status IN ('reserved','finalized'))>=COALESCE(s.shorts,CASE u.plan
       WHEN 'creator' THEN 15 WHEN 'growth' THEN 50 WHEN 'pro' THEN 150
       WHEN 'mini_pass' THEN 5 WHEN 'agency' THEN 500 ELSE 2 END))
    ON CONFLICT(kind,resource_id) DO UPDATE SET status='reserved',updated_at=excluded.updated_at
      WHERE credit_topup_spends.status='released' AND credit_topup_spends.user_id=excluded.user_id;

  SELECT CASE WHEN (COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)+(NEW.duration/60.0)) > (COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)))+(CASE WHEN (SELECT u.plan FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)) IN ('creator','growth','pro','agency') THEN COALESCE((SELECT w.minutes_balance FROM credit_topup_wallets w WHERE w.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)),0) ELSE 0 END)+0.0000001)
    THEN RAISE(ABORT,'KARO_MINUTES_QUOTA_EXCEEDED') END;
  UPDATE credit_topup_wallets SET minutes_balance=minutes_balance-(MAX(0,(COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)+(NEW.duration/60.0))-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))))-MAX(0,COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))))),
    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND (MAX(0,(COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)+(NEW.duration/60.0))-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))))-MAX(0,COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)))))>0.0000001;
  INSERT INTO credit_topup_spends(user_id,kind,resource_id,amount,status,created_at,updated_at)
    SELECT (SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id),'minutes',NEW.project_id,(MAX(0,(COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)+(NEW.duration/60.0))-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))))-MAX(0,COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))))),'reserved',
      strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE (MAX(0,(COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)+(NEW.duration/60.0))-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))))-MAX(0,COALESCE((SELECT us.source_minutes FROM usage us WHERE us.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND us.month=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),0)-COALESCE((SELECT s.processing_minutes FROM plan_entitlement_snapshots s WHERE s.user_id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id) AND s.period_key=(SELECT CASE WHEN u.plan='free' THEN 'free:' || strftime('%Y-%m','now') ELSE
  u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
  substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id))),
  (SELECT CASE u.plan WHEN 'creator' THEN 120.0 WHEN 'growth' THEN 300.0 WHEN 'pro' THEN 600.0
    WHEN 'mini_pass' THEN 25.0 WHEN 'agency' THEN 1500.0 ELSE 15.0 END FROM users u WHERE u.id=(SELECT p.user_id FROM projects p WHERE p.id=NEW.project_id)))))>0.0000001
    ON CONFLICT(kind,resource_id) DO UPDATE SET
      amount=excluded.amount,status='reserved',updated_at=excluded.updated_at
      WHERE credit_topup_spends.status='released' AND credit_topup_spends.user_id=excluded.user_id;

  UPDATE usage SET source_minutes=source_minutes + (NEW.duration / 60.0)
  WHERE user_id=(SELECT user_id FROM projects WHERE id=NEW.project_id)
    AND month=(
      SELECT CASE WHEN u.plan='free'
        THEN 'free:' || strftime('%Y-%m','now')
        ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
             substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
      END
      FROM projects p JOIN users u ON u.id=p.user_id WHERE p.id=NEW.project_id
    );

  INSERT INTO usage_reservations(id,user_id,period_key,kind,amount,resource_id,status,created_at,updated_at)
  SELECT lower(hex(randomblob(16))), p.user_id,
    CASE WHEN u.plan='free'
      THEN 'free:' || strftime('%Y-%m','now')
      ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
           substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
    END,
    'minutes', NEW.duration / 60.0, NEW.project_id, 'reserved',
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
  FROM projects p JOIN users u ON u.id=p.user_id WHERE p.id=NEW.project_id;
END;

-- Successful project completion finalizes the reservation. The quota was
-- already deducted at reserve time, so no second usage increment occurs here.
CREATE TRIGGER IF NOT EXISTS trg_finalize_project_minutes
AFTER UPDATE OF status ON projects
WHEN NEW.status='ready' AND OLD.status <> 'ready'
BEGIN
  UPDATE usage_reservations SET status='finalized',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE kind='minutes' AND resource_id=NEW.id AND status='reserved';
END;

-- Failed or deleted projects refund only still-reserved minutes. Finalized
-- usage is never refunded by a later retry/delete.
CREATE TRIGGER IF NOT EXISTS trg_release_failed_project_minutes
BEFORE UPDATE OF status ON projects
WHEN NEW.status='failed' AND OLD.status <> 'failed'
BEGIN
  UPDATE usage SET source_minutes=MAX(0,source_minutes-COALESCE((
    SELECT SUM(r.amount) FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='minutes' AND r.resource_id=NEW.id AND r.status='reserved'
  ),0))
  WHERE EXISTS (
    SELECT 1 FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='minutes' AND r.resource_id=NEW.id AND r.status='reserved'
  );
  UPDATE usage_reservations SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE kind='minutes' AND resource_id=NEW.id AND status='reserved';
END;

CREATE TRIGGER IF NOT EXISTS trg_release_deleted_project_minutes
BEFORE DELETE ON projects
BEGIN
  UPDATE usage SET source_minutes=MAX(0,source_minutes-COALESCE((
    SELECT SUM(r.amount) FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='minutes' AND r.resource_id=OLD.id AND r.status='reserved'
  ),0))
  WHERE EXISTS (
    SELECT 1 FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='minutes' AND r.resource_id=OLD.id AND r.status='reserved'
  );
  UPDATE usage_reservations SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE kind='minutes' AND resource_id=OLD.id AND status='reserved';
END;

-- New-price paid plans spend one Short only on first export of a distinct clip.
-- Legacy subscriptions and existing Mini Passes retain previously bought rights.
DROP TRIGGER IF EXISTS trg_reserve_paid_short;
CREATE TRIGGER trg_reserve_paid_short
BEFORE INSERT ON exports
WHEN EXISTS(
  SELECT 1 FROM users u JOIN plan_entitlement_snapshots s ON s.user_id=u.id
  WHERE u.id=NEW.user_id AND u.plan NOT IN ('free','agency')
    AND s.short_mode='finished_shorts'
    AND s.period_key=(u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local')
      || ':' || substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19))
)
BEGIN
  SELECT CASE WHEN EXISTS(
    SELECT 1 FROM short_credit_reservations r
    WHERE r.user_id=NEW.user_id AND r.clip_id=NEW.clip_id
      AND r.status='reserved'
  ) THEN RAISE(ABORT,'SHORT_RENDER_ALREADY_RESERVED') END;

  SELECT CASE WHEN NOT EXISTS(
    SELECT 1 FROM short_credit_reservations r
    WHERE r.user_id=NEW.user_id AND r.clip_id=NEW.clip_id
      AND r.status='finalized'
  ) AND NOT EXISTS(
    SELECT 1 FROM exports e WHERE e.user_id=NEW.user_id
      AND e.clip_id=NEW.clip_id AND e.status='ready'
  ) AND (
    SELECT COUNT(DISTINCT clip_id) FROM short_credit_reservations r
    WHERE r.user_id=NEW.user_id AND r.status IN ('reserved','finalized')
      AND r.period_key=(
        SELECT u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local')
          || ':' || substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
        FROM users u WHERE u.id=NEW.user_id
      )
  ) >= (
    SELECT s.shorts FROM plan_entitlement_snapshots s JOIN users u ON u.id=s.user_id
    WHERE u.id=NEW.user_id AND s.period_key=(
      u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local')
      || ':' || substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19))
  ) AND COALESCE((SELECT w.shorts_balance FROM credit_topup_wallets w WHERE w.user_id=NEW.user_id),0)<=0
  THEN RAISE(ABORT,'AI_SHORT_QUOTA_EXCEEDED') END;  UPDATE credit_topup_wallets SET shorts_balance=shorts_balance-1,
    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE user_id=NEW.user_id AND NOT EXISTS(SELECT 1 FROM short_credit_reservations r WHERE r.user_id=NEW.user_id AND r.clip_id=NEW.clip_id
      AND r.status='finalized') AND NOT EXISTS(SELECT 1 FROM exports e WHERE e.user_id=NEW.user_id
      AND e.clip_id=NEW.clip_id AND e.status='ready') AND
    (SELECT COUNT(*) FROM short_credit_reservations r WHERE r.user_id=NEW.user_id
      AND r.period_key=(SELECT u.plan||':'||COALESCE(NULLIF(u.billing_reference,''),u.id,'local')||':'||
        substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) FROM users u WHERE u.id=NEW.user_id)
      AND r.status IN ('reserved','finalized')) >=
    (SELECT s.shorts FROM plan_entitlement_snapshots s JOIN users u ON u.id=s.user_id
      WHERE u.id=NEW.user_id AND s.period_key=(u.plan||':'||COALESCE(NULLIF(u.billing_reference,''),u.id,'local')||':'||
        substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)));
  INSERT INTO credit_topup_spends(user_id,kind,resource_id,amount,status,created_at,updated_at)
    SELECT NEW.user_id,'shorts',NEW.id,1,'reserved',
    strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE NOT EXISTS(SELECT 1 FROM short_credit_reservations r WHERE r.user_id=NEW.user_id AND r.clip_id=NEW.clip_id
      AND r.status='finalized') AND NOT EXISTS(SELECT 1 FROM exports e WHERE e.user_id=NEW.user_id
      AND e.clip_id=NEW.clip_id AND e.status='ready') AND
    (SELECT COUNT(*) FROM short_credit_reservations r WHERE r.user_id=NEW.user_id
      AND r.period_key=(SELECT u.plan||':'||COALESCE(NULLIF(u.billing_reference,''),u.id,'local')||':'||
        substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19) FROM users u WHERE u.id=NEW.user_id)
      AND r.status IN ('reserved','finalized')) >=
    (SELECT s.shorts FROM plan_entitlement_snapshots s JOIN users u ON u.id=s.user_id
      WHERE u.id=NEW.user_id AND s.period_key=(u.plan||':'||COALESCE(NULLIF(u.billing_reference,''),u.id,'local')||':'||
        substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)))
    ON CONFLICT(kind,resource_id) DO UPDATE SET status='reserved',updated_at=excluded.updated_at
      WHERE credit_topup_spends.status='released' AND credit_topup_spends.user_id=excluded.user_id;

  INSERT INTO short_credit_reservations
    (clip_id,user_id,period_key,export_id,status,created_at,updated_at)
  SELECT NEW.clip_id,u.id,u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local')
      || ':' || substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19),
    NEW.id,'reserved',strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
  FROM users u WHERE u.id=NEW.user_id
    AND NOT EXISTS(SELECT 1 FROM short_credit_reservations r WHERE r.user_id=NEW.user_id
      AND r.clip_id=NEW.clip_id AND r.status='finalized')
    AND NOT EXISTS(SELECT 1 FROM exports e WHERE e.user_id=NEW.user_id
      AND e.clip_id=NEW.clip_id AND e.status='ready')
  ON CONFLICT(clip_id) DO UPDATE SET
    period_key=excluded.period_key,export_id=excluded.export_id,status='reserved',
    updated_at=excluded.updated_at
  WHERE short_credit_reservations.status='released'
    AND short_credit_reservations.user_id=excluded.user_id;
END;

DROP TRIGGER IF EXISTS trg_finalize_paid_short;
CREATE TRIGGER trg_finalize_paid_short AFTER UPDATE OF status ON exports
WHEN NEW.status='ready' AND OLD.status<>'ready'
BEGIN
  UPDATE short_credit_reservations SET status='finalized',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE user_id=NEW.user_id AND clip_id=NEW.clip_id AND export_id=NEW.id AND status='reserved';
END;

DROP TRIGGER IF EXISTS trg_release_failed_paid_short;
CREATE TRIGGER trg_release_failed_paid_short BEFORE UPDATE OF status ON exports
WHEN NEW.status IN ('failed','expired') AND OLD.status<>NEW.status
BEGIN
  UPDATE short_credit_reservations SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE user_id=NEW.user_id AND clip_id=NEW.clip_id AND export_id=NEW.id AND status='reserved';
END;

DROP TRIGGER IF EXISTS trg_release_deleted_paid_short;
CREATE TRIGGER trg_release_deleted_paid_short BEFORE DELETE ON exports
BEGIN
  UPDATE short_credit_reservations SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE user_id=OLD.user_id AND clip_id=OLD.clip_id AND export_id=OLD.id AND status='reserved';
END;

-- Per-job purchased credit reservations are settled independently of base plan usage.
CREATE TRIGGER IF NOT EXISTS trg_finalize_purchased_project AFTER UPDATE OF status ON projects
WHEN NEW.status='ready' AND OLD.status<>'ready'
BEGIN
  UPDATE credit_topup_spends SET status='finalized',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE resource_id=NEW.id AND status='reserved';
END;
CREATE TRIGGER IF NOT EXISTS trg_release_purchased_project AFTER UPDATE OF status ON projects
WHEN NEW.status='failed' AND OLD.status<>'failed'
BEGIN
  UPDATE credit_topup_wallets SET minutes_balance=minutes_balance+COALESCE((SELECT SUM(amount) FROM credit_topup_spends
      WHERE resource_id=NEW.id AND user_id=credit_topup_wallets.user_id AND kind='minutes' AND status='reserved'),0),
    shorts_balance=shorts_balance+COALESCE((SELECT SUM(amount) FROM credit_topup_spends
      WHERE resource_id=NEW.id AND user_id=credit_topup_wallets.user_id AND kind='shorts' AND status='reserved'),0)
    WHERE user_id=NEW.user_id;
  UPDATE credit_topup_spends SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE resource_id=NEW.id AND status='reserved';
END;
CREATE TRIGGER IF NOT EXISTS trg_delete_purchased_project BEFORE DELETE ON projects
BEGIN
  UPDATE credit_topup_wallets SET minutes_balance=minutes_balance+COALESCE((SELECT SUM(amount) FROM credit_topup_spends
      WHERE resource_id=OLD.id AND user_id=credit_topup_wallets.user_id AND kind='minutes' AND status='reserved'),0),
    shorts_balance=shorts_balance+COALESCE((SELECT SUM(amount) FROM credit_topup_spends
      WHERE resource_id=OLD.id AND user_id=credit_topup_wallets.user_id AND kind='shorts' AND status='reserved'),0)
    WHERE user_id=OLD.user_id;
  UPDATE credit_topup_spends SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE resource_id=OLD.id AND status='reserved';
END;
CREATE TRIGGER IF NOT EXISTS trg_finalize_purchased_export AFTER UPDATE OF status ON exports
WHEN NEW.status='ready' AND OLD.status<>'ready'
BEGIN
  UPDATE credit_topup_spends SET status='finalized',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE resource_id=NEW.id AND status='reserved';
END;
CREATE TRIGGER IF NOT EXISTS trg_release_purchased_export AFTER UPDATE OF status ON exports
WHEN NEW.status IN ('failed','expired') AND OLD.status<>NEW.status
BEGIN
  UPDATE credit_topup_wallets SET shorts_balance=shorts_balance+COALESCE((SELECT SUM(amount) FROM credit_topup_spends
    WHERE resource_id=NEW.id AND user_id=credit_topup_wallets.user_id AND kind='shorts' AND status='reserved'),0)
    WHERE user_id=NEW.user_id;
  UPDATE credit_topup_spends SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE resource_id=NEW.id AND status='reserved';
END;
CREATE TRIGGER IF NOT EXISTS trg_delete_purchased_export BEFORE DELETE ON exports
BEGIN
  UPDATE credit_topup_wallets SET shorts_balance=shorts_balance+COALESCE((SELECT SUM(amount) FROM credit_topup_spends
    WHERE resource_id=OLD.id AND user_id=credit_topup_wallets.user_id AND kind='shorts' AND status='reserved'),0)
    WHERE user_id=OLD.user_id;
  UPDATE credit_topup_spends SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE resource_id=OLD.id AND status='reserved';
END;

-- Paid plans render and re-render without consuming AI Short creation credits.
-- Free keeps a small render allowance to bound unpaid FFmpeg compute.
DROP TRIGGER IF EXISTS trg_reserve_export;
CREATE TRIGGER trg_reserve_export
BEFORE INSERT ON exports
WHEN (SELECT plan FROM users WHERE id=NEW.user_id)='free'
BEGIN
  INSERT OR IGNORE INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit)
  SELECT lower(hex(randomblob(16))), u.id,
    CASE WHEN u.plan='free'
      THEN 'free:' || strftime('%Y-%m','now')
      ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
           substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
    END,
    0, 0,
    CASE u.plan
      WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50
      WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END
  FROM users u WHERE u.id=NEW.user_id;

  UPDATE usage SET exports_limit=(
    SELECT CASE u.plan
      WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50
      WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END
    FROM users u WHERE u.id=NEW.user_id
  )
  WHERE user_id=NEW.user_id AND month=(
    SELECT CASE WHEN u.plan='free'
      THEN 'free:' || strftime('%Y-%m','now')
      ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
           substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
    END FROM users u WHERE u.id=NEW.user_id
  );

  SELECT CASE WHEN (
    SELECT COALESCE(us.exports_used,0) >=
      CASE u.plan
        WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15 WHEN 'growth' THEN 50
        WHEN 'pro' THEN 150 WHEN 'agency' THEN 500 ELSE 2 END
    FROM users u LEFT JOIN usage us ON us.user_id=u.id AND us.month=(
      CASE WHEN u.plan='free'
        THEN 'free:' || strftime('%Y-%m','now')
        ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
             substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
      END
    ) WHERE u.id=NEW.user_id
  ) THEN RAISE(ABORT,'SHORT_EXPORT_QUOTA_EXCEEDED') END;

  UPDATE usage SET exports_used=exports_used+1
  WHERE user_id=NEW.user_id AND month=(
    SELECT CASE WHEN u.plan='free'
      THEN 'free:' || strftime('%Y-%m','now')
      ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
           substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
    END FROM users u WHERE u.id=NEW.user_id
  );

  INSERT INTO usage_reservations(id,user_id,period_key,kind,amount,resource_id,status,created_at,updated_at)
  SELECT lower(hex(randomblob(16))), u.id,
    CASE WHEN u.plan='free'
      THEN 'free:' || strftime('%Y-%m','now')
      ELSE u.plan || ':' || COALESCE(NULLIF(u.billing_reference,''),u.id,'local') || ':' ||
           substr(COALESCE(u.plan_started_at,strftime('%Y-%m','now')),1,19)
    END,
    'export',1,NEW.id,'reserved',strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
  FROM users u WHERE u.id=NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_finalize_export
AFTER UPDATE OF status ON exports
WHEN NEW.status='ready' AND OLD.status <> 'ready'
BEGIN
  UPDATE usage_reservations SET status='finalized',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE kind='export' AND resource_id=NEW.id AND status='reserved';
END;

CREATE TRIGGER IF NOT EXISTS trg_release_failed_export
BEFORE UPDATE OF status ON exports
WHEN NEW.status='failed' AND OLD.status <> 'failed'
BEGIN
  UPDATE usage SET exports_used=MAX(0,exports_used-CAST(COALESCE((
    SELECT SUM(r.amount) FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='export' AND r.resource_id=NEW.id AND r.status='reserved'
  ),0) AS INTEGER))
  WHERE EXISTS (
    SELECT 1 FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='export' AND r.resource_id=NEW.id AND r.status='reserved'
  );
  UPDATE usage_reservations SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE kind='export' AND resource_id=NEW.id AND status='reserved';
END;

CREATE TRIGGER IF NOT EXISTS trg_release_deleted_export
BEFORE DELETE ON exports
BEGIN
  UPDATE usage SET exports_used=MAX(0,exports_used-CAST(COALESCE((
    SELECT SUM(r.amount) FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='export' AND r.resource_id=OLD.id AND r.status='reserved'
  ),0) AS INTEGER))
  WHERE EXISTS (
    SELECT 1 FROM usage_reservations r
    WHERE r.user_id=usage.user_id AND r.period_key=usage.month
      AND r.kind='export' AND r.resource_id=OLD.id AND r.status='reserved'
  );
  UPDATE usage_reservations SET status='released',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE kind='export' AND resource_id=OLD.id AND status='reserved';
END;
"""


def _normalize(query: str) -> str:
    return " ".join(query.lower().split())


def _prepare_query(query: str) -> str | None:
    normalized = _normalize(query)
    # Atomic reservation triggers own successful usage accounting. These two
    # statements are retained in older route code for backward compatibility;
    # executing them would double-charge a reservation, so they are ignored.
    if normalized.startswith("update usage set source_minutes=source_minutes+?"):
        return None
    if normalized.startswith("update usage set exports_used=exports_used+1"):
        return None
    # Concurrent first reads may both attempt to create the same usage period.
    if normalized.startswith("insert into usage(id,user_id,month,source_minutes,exports_used,exports_limit)"):
        return query.replace("INSERT INTO usage", "INSERT OR IGNORE INTO usage", 1)
    return query


def _translate_quota_error(exc: Exception) -> None:
    message = str(exc)
    if "AI_SHORT_QUOTA_EXCEEDED" in message:
        raise UsageQuotaExceeded(
            "No AI Short creation credits remain after accounting for reserved or finalized creations. "
            "Existing Shorts can still be edited, exported and re-exported."
        ) from exc
    if "SHORT_RENDER_ALREADY_RESERVED" in message:
        raise UsageQuotaExceeded(
            "This Short is already rendering. Wait for the existing render to finish."
        ) from exc
    if "KARO_MINUTES_QUOTA_EXCEEDED" in message:
        raise UsageQuotaExceeded(
            "Not enough Karo Minutes remain after accounting for videos already queued or processing. "
            "Wait for failed jobs to refund their reservation, upgrade, or wait for your quota to refresh."
        ) from exc
    if "SHORT_EXPORT_QUOTA_EXCEEDED" in message:
        raise UsageQuotaExceeded(
            "Your Free export allowance is fully used or reserved by exports already queued or rendering. "
            "Wait for a failed render to refund its slot, or upgrade for unlimited exports and re-exports."
        ) from exc


def _is_transient_lock_error(exc: BaseException) -> bool:
    """Return True only for retry-safe SQLite BUSY/LOCKED failures."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, sqlite3.OperationalError):
            code = getattr(current, "sqlite_errorcode", None)
            if isinstance(code, int) and (code & 0xFF) in _LOCK_PRIMARY_CODES:
                return True
            message = str(current).lower()
            if any(fragment in message for fragment in _LOCK_MESSAGES):
                return True
        current = current.__cause__ or current.__context__
    return False


def _retry_delay_seconds(attempt: int) -> float:
    settings = get_settings()
    base_ms = max(1, int(settings.sqlite_lock_retry_base_ms))
    # Lock storms should recover quickly, but never create an unbounded sleep.
    return min(0.5, (base_ms * (2 ** max(0, attempt - 1))) / 1000.0)


async def _run_with_lock_retry(operation: Callable[[], Awaitable[T]], *, operation_name: str) -> T:
    """Retry a complete database operation only for transient SQLite locks.

    Each attempt must create its own connection/transaction. That guarantees a
    failed transaction is rolled back before retry and prevents partial state
    from leaking across attempts.
    """
    max_attempts = max(1, int(get_settings().sqlite_lock_max_attempts))
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            _translate_quota_error(exc)
            if not _is_transient_lock_error(exc) or attempt >= max_attempts:
                raise
            delay = _retry_delay_seconds(attempt)
            logger.warning(
                "SQLite contention during %s; retrying in %.3fs (%d/%d)",
                operation_name, delay, attempt + 1, max_attempts,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("SQLite retry loop exited unexpectedly.")


async def _configure(db: aiosqlite.Connection) -> None:
    settings = get_settings()
    busy_timeout_ms = max(0, int(settings.sqlite_busy_timeout_ms))
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    # WAL + NORMAL keeps readers non-blocking during writes while avoiding the
    # fsync cost of FULL for every commit. WAL itself is persisted by init_db.
    await db.execute("PRAGMA synchronous = NORMAL")


async def _close_connection(db: aiosqlite.Connection) -> None:
    """Close SQLite and wait until aiosqlite's worker has fully stopped.

    aiosqlite 0.22+ awaits its stop sentinel during `close()`, while older
    releases exposed the Connection itself as the worker thread. Joining the
    actual worker as a final barrier keeps short-lived event loops from closing
    while a queued result is still trying to report back to them.
    """
    close_task = asyncio.create_task(db.close())
    try:
        await asyncio.shield(close_task)
    except asyncio.CancelledError:
        # A cancelled request must still finish closing the DB worker before the
        # event loop disappears; then propagate the cancellation unchanged.
        await close_task
        raise

    worker = getattr(db, "_thread", db)
    is_alive = getattr(worker, "is_alive", None)
    join = getattr(worker, "join", None)
    if callable(is_alive) and callable(join) and is_alive():
        await asyncio.to_thread(join)


async def _open_connection() -> aiosqlite.Connection:
    settings = get_settings()
    timeout_seconds = max(0.001, int(settings.sqlite_busy_timeout_ms) / 1000.0)
    db = await aiosqlite.connect(settings.database_path, timeout=timeout_seconds)
    try:
        await _configure(db)
    except Exception:
        await _close_connection(db)
        raise
    return db


async def init_db() -> None:
    settings = get_settings()
    if settings.normalized_database_backend == "postgres":
        pool = await _get_postgres_pool()
        async with pool.acquire() as connection:
            revision = await connection.fetchval(
                "SELECT version_num FROM alembic_version LIMIT 1"
            )
        # The NVIDIA credential expansion is additive. Accept the previous
        # revision during deployment, while the save route waits for the expansion.
        if revision not in {POSTGRES_SCHEMA_REVISION, POSTGRES_PREVIOUS_SCHEMA_REVISION}:
            raise RuntimeError(
                "PostgreSQL schema is not current. Run `alembic upgrade head` before starting ClipKaro."
            )
        return
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    async def _initialize() -> None:
        db = await _open_connection()
        try:
            await db.executescript(SCHEMA)
            # Safe in-place migration for existing ClipKaro databases created before billing v2.
            columns = {row[1] for row in await (await db.execute("PRAGMA table_info(users)")).fetchall()}
            migrations = {
                "billing_reference": "ALTER TABLE users ADD COLUMN billing_reference TEXT",
                "plan_started_at": "ALTER TABLE users ADD COLUMN plan_started_at TEXT",
                "plan_expires_at": "ALTER TABLE users ADD COLUMN plan_expires_at TEXT",
                "cancel_at_period_end": "ALTER TABLE users ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0",
                "post_karo_access_override": "ALTER TABLE users ADD COLUMN post_karo_access_override INTEGER NOT NULL DEFAULT 0",
                "cartoon_studio_access_override": "ALTER TABLE users ADD COLUMN cartoon_studio_access_override INTEGER NOT NULL DEFAULT 0",
            }
            for name, statement in migrations.items():
                if name not in columns:
                    await db.execute(statement)
            # Source and export object generations were present in PostgreSQL
            # but omitted from the SQLite schema. Both new and pre-existing
            # local databases must support the same upload/detail queries.
            for table in ("videos", "exports"):
                media_columns = {
                    row[1] for row in await (
                        await db.execute(f"PRAGMA table_info({table})")
                    ).fetchall()
                }
                if "object_generation" not in media_columns:
                    await db.execute(
                        f"ALTER TABLE {table} ADD COLUMN object_generation TEXT"
                    )
            # Upgrade a pre-existing SQLite installation without removing
            # any old purchased minutes, prior Razorpay plan IDs or legacy terms.
            await db.execute("""INSERT OR IGNORE INTO billing_plan_versions
                (provider_plan_id,plan_key,amount,currency,created_at)
                SELECT provider_plan_id,plan_key,amount,currency,created_at FROM billing_plans""")
            await db.execute("""INSERT OR IGNORE INTO legacy_billing_subscriptions
                (subscription_id,plan_key)
                SELECT billing_reference,plan FROM users
                WHERE billing_reference LIKE 'sub_%' AND plan IN ('creator','growth','pro')""")
            # Pending checkouts can be captured AFTER the new prices go live.
            # Freeze old-price benefits from the historic checkout itself.
            await db.execute("""INSERT OR IGNORE INTO checkout_entitlement_snapshots
              (checkout_id,processing_minutes,shorts,source_video_limit_minutes,
               short_mode,price_paise,created_at)
              SELECT id,CASE plan
                WHEN 'mini_pass' THEN 125 WHEN 'creator' THEN 60
                WHEN 'growth' THEN 180 WHEN 'pro' THEN 480 ELSE 1500 END,
                CASE plan WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15
                  WHEN 'growth' THEN 50 WHEN 'pro' THEN 150 ELSE 500 END,
                CASE plan WHEN 'mini_pass' THEN 25 WHEN 'creator' THEN 60
                  WHEN 'growth' THEN 180 WHEN 'pro' THEN 240 ELSE 240 END,
                'source_projects',amount,created_at FROM billing_checkouts
              WHERE status IN ('created','authorized')
                AND plan IN ('mini_pass','creator','growth','pro','agency')""")
            await db.execute("""INSERT OR IGNORE INTO plan_entitlement_snapshots
                (user_id,period_key,plan_key,processing_minutes,shorts,
                source_video_limit_minutes,short_mode,price_paise,created_at)
                SELECT id,
                  plan || ':' || COALESCE(NULLIF(billing_reference,''),id,'local')
                    || ':' || substr(COALESCE(plan_started_at,strftime('%Y-%m','now')),1,19),
                  plan,
                  CASE plan WHEN 'mini_pass' THEN 125 WHEN 'creator' THEN 60
                    WHEN 'growth' THEN 180 WHEN 'pro' THEN 480 ELSE 1500 END,
                  CASE plan WHEN 'mini_pass' THEN 5 WHEN 'creator' THEN 15
                    WHEN 'growth' THEN 50 WHEN 'pro' THEN 150 ELSE 500 END,
                  CASE plan WHEN 'mini_pass' THEN 25 WHEN 'creator' THEN 60
                    WHEN 'growth' THEN 180 WHEN 'pro' THEN 240 ELSE 240 END,
                  'source_projects',
                  CASE plan WHEN 'mini_pass' THEN 5900 WHEN 'creator' THEN 19900
                    WHEN 'growth' THEN 39900 WHEN 'pro' THEN 79900 ELSE 199900 END,
                  strftime('%Y-%m-%dT%H:%M:%fZ','now')
                FROM users
                WHERE plan IN ('mini_pass','creator','growth','pro')
                  AND billing_reference IS NOT NULL""")
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await _close_connection(db)

    await _run_with_lock_retry(_initialize, operation_name="database initialization")
    # Quota tables must exist even when the private preview rollout is OFF:
    # normal subscription upgrades also migrate the isolated credit period.
    from app.services.smart_layout_credits import init_smart_layout_credits
    await init_smart_layout_credits()


async def run_in_transaction(
    operation: Callable[[Any], Awaitable[T]],
    *,
    mode: str = "IMMEDIATE",
    operation_name: str = "transaction",
) -> T:
    """Run and retry a complete SQLite transaction as one atomic unit.

    `IMMEDIATE` acquires the write reservation before any business reads/writes,
    so quota-sensitive transactions cannot do work against a stale snapshot and
    then fail halfway through lock acquisition. The callback must not commit or
    call this helper recursively on the same logical transaction.
    """
    if get_settings().normalized_database_backend == "postgres":
        pool = await _get_postgres_pool()
        async with pool.acquire() as raw:
            async with raw.transaction():
                return await operation(_PostgresConnection(raw))

    transaction_mode = mode.upper()
    if transaction_mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:
        raise ValueError("SQLite transaction mode must be DEFERRED, IMMEDIATE, or EXCLUSIVE.")

    async def _attempt() -> T:
        db = await _open_connection()
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(f"BEGIN {transaction_mode}")
            result = await operation(db)
            await db.commit()
            return result
        except Exception:
            try:
                await db.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            await _close_connection(db)

    return await _run_with_lock_retry(_attempt, operation_name=operation_name)


async def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    prepared = _prepare_query(query)
    if prepared is None:
        return

    async def _write(db: aiosqlite.Connection) -> None:
        await db.execute(prepared, params)

    await run_in_transaction(_write, mode="IMMEDIATE", operation_name="single write")


async def execute_many(query: str, rows: Iterable[tuple[Any, ...]]) -> None:
    prepared = _prepare_query(query)
    if prepared is None:
        return
    # Materialize once because a generator would be exhausted if a lock forces
    # the entire transaction to retry.
    materialized_rows = tuple(rows)

    async def _write_many(db: aiosqlite.Connection) -> None:
        await db.executemany(prepared, materialized_rows)

    await run_in_transaction(_write_many, mode="IMMEDIATE", operation_name="batch write")


async def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    if get_settings().normalized_database_backend == "postgres":
        pool = await _get_postgres_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(_postgres_query(query), *params)
            return dict(row) if row else None

    async def _read() -> dict[str, Any] | None:
        db = await _open_connection()
        db.row_factory = aiosqlite.Row
        try:
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        finally:
            await _close_connection(db)

    return await _run_with_lock_retry(_read, operation_name="single read")


async def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if get_settings().normalized_database_backend == "postgres":
        pool = await _get_postgres_pool()
        async with pool.acquire() as connection:
            return [dict(row) for row in await connection.fetch(_postgres_query(query), *params)]

    async def _read_all() -> list[dict[str, Any]]:
        db = await _open_connection()
        db.row_factory = aiosqlite.Row
        try:
            async with db.execute(query, params) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
        finally:
            await _close_connection(db)

    return await _run_with_lock_retry(_read_all, operation_name="multi-row read")

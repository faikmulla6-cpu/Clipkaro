from __future__ import annotations

from app.core.config import get_settings
from app.core.database import run_in_transaction


async def init_cartoon_studio() -> None:
    """Install local SQLite tables. PostgreSQL production schema is Alembic-owned."""
    if get_settings().normalized_database_backend == "postgres":
        return

    async def _migrate(db) -> None:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS cartoon_provider_credentials (
                 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                 provider TEXT NOT NULL CHECK(provider IN ('openrouter','nvidia')),
                 api_key_ciphertext TEXT NOT NULL,
                 api_key_masked TEXT NOT NULL,
                 api_key_fingerprint TEXT NOT NULL,
                 validated_at TEXT NOT NULL,
                 created_at TEXT NOT NULL,
                 updated_at TEXT NOT NULL,
                 PRIMARY KEY(user_id, provider)
               )"""
        )
        cursor = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='cartoon_provider_credentials'"
        )
        table = await cursor.fetchone()
        sql = table[0] if table else ""
        if sql and "'nvidia'" not in sql:
            replacement = sql.replace("cartoon_provider_credentials", "cartoon_provider_credentials_new", 1)
            replacement = replacement.replace("'openrouter'", "'openrouter','nvidia'")
            await db.execute(replacement)
            await db.execute("INSERT INTO cartoon_provider_credentials_new SELECT * FROM cartoon_provider_credentials")
            await db.execute("DROP TABLE cartoon_provider_credentials")
            await db.execute("ALTER TABLE cartoon_provider_credentials_new RENAME TO cartoon_provider_credentials")
        await db.execute(
            """CREATE TABLE IF NOT EXISTS cartoon_projects (
                 id TEXT PRIMARY KEY,
                 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                 job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
                 title TEXT NOT NULL,
                 prompt TEXT NOT NULL,
                 duration_seconds INTEGER NOT NULL CHECK(duration_seconds BETWEEN 15 AND 60),
                 aspect_ratio TEXT NOT NULL CHECK(aspect_ratio IN ('9:16','16:9','1:1','4:5')),
                 style TEXT NOT NULL,
                 language TEXT NOT NULL,
                 text_model TEXT NOT NULL,
                 tts_model TEXT NOT NULL,
                 status TEXT NOT NULL DEFAULT 'queued'
                   CHECK(status IN ('queued','processing','ready','failed')),
                 progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                 stage TEXT NOT NULL DEFAULT 'queued',
                 storyboard_json TEXT NOT NULL DEFAULT '{}',
                 assets_json TEXT NOT NULL DEFAULT '{}',
                 reference_key TEXT,
                 reference_generation TEXT,
                 output_key TEXT,
                 output_generation TEXT,
                 error TEXT,
                 created_at TEXT NOT NULL,
                 updated_at TEXT NOT NULL
               )"""
        )
        cursor = await db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cartoon_projects'")
        table = await cursor.fetchone()
        sql = table[0] if table else ""
        if sql and "'4:5'" not in sql:
            # SQLite cannot alter CHECK constraints. Copy every row inside this transaction.
            replacement = sql.replace("cartoon_projects", "cartoon_projects_v3", 1).replace("'1:1'", "'1:1','4:5'")
            await db.execute(replacement)
            await db.execute("INSERT INTO cartoon_projects_v3 SELECT * FROM cartoon_projects")
            await db.execute("DROP TABLE cartoon_projects")
            await db.execute("ALTER TABLE cartoon_projects_v3 RENAME TO cartoon_projects")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_cartoon_projects_user_created "
            "ON cartoon_projects(user_id, created_at DESC)"
        )

    await run_in_transaction(_migrate, operation_name="cartoon studio schema migration")

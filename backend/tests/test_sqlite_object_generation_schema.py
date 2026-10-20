"""SQLite media storage generation columns match PostgreSQL on create/upgrade."""
import sqlite3
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.database import init_db


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.asyncio
async def test_sqlite_media_generation_columns_created_and_upgraded(
    tmp_path: Path, legacy: bool
):
    cfg = get_settings()
    original = (cfg.database_path, cfg.app_env, cfg.storage_root, cfg.database_backend)
    cfg.database_path = tmp_path / "clipkaro.db"
    cfg.storage_root = tmp_path / "storage"
    cfg.app_env = "test"
    cfg.database_backend = "sqlite"
    if legacy:
        with sqlite3.connect(cfg.database_path) as conn:
            conn.executescript("""
            CREATE TABLE videos (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                original_filename TEXT NOT NULL, file_path TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            CREATE TABLE exports (
                id TEXT PRIMARY KEY, clip_id TEXT NOT NULL, user_id TEXT NOT NULL,
                output_path TEXT NOT NULL, resolution TEXT NOT NULL,
                caption_style TEXT NOT NULL, watermark INTEGER NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            INSERT INTO videos VALUES
                ('legacy-video','old-project','old.mp4','old-key','uploaded','a','b');
            """)
    try:
        await init_db()
        with sqlite3.connect(cfg.database_path) as conn:
            for table in ("videos", "exports"):
                columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                assert "object_generation" in columns, table
            if legacy:
                assert conn.execute(
                    "SELECT file_path,object_generation FROM videos WHERE id=?",
                    ("legacy-video",)
                ).fetchone() == ("old-key", None)
        # It is safe to initialize the same database repeatedly.
        await init_db()
    finally:
        cfg.database_path, cfg.app_env, cfg.storage_root, cfg.database_backend = original

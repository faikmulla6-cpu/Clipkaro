from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="POSTGRES_TEST_URL is not configured")


def _migration_schema() -> str:
    path = Path(__file__).resolve().parents[1] / "migrations/versions/20260817_01_no_vps_schema.py"
    spec = importlib.util.spec_from_file_location("clipkaro_pg_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.SCHEMA


def test_postgres_quota_reservation_is_atomic_across_connections() -> None:
    async def scenario() -> None:
        import asyncpg

        schema_name = "ck_test_" + uuid.uuid4().hex[:12]
        admin = await asyncpg.connect(POSTGRES_TEST_URL)
        try:
            await admin.execute(f'CREATE SCHEMA "{schema_name}"')
            await admin.execute(f'SET search_path TO "{schema_name}"')
            await admin.execute(_migration_schema())
            now = "2026-08-17T00:00:00+00:00"
            await admin.execute("INSERT INTO users(id,name,email,password_hash,created_at,updated_at) VALUES('u','User','u@example.test','hash',$1,$1)", now)
            for suffix in ("1", "2"):
                await admin.execute("INSERT INTO projects(id,user_id,title,status,created_at,updated_at,stage) VALUES($1,'u','p','queued',$2,$2,'queued')", "p" + suffix, now)
                await admin.execute("INSERT INTO videos(id,project_id,original_filename,duration,file_size,file_path,status,created_at,expires_at) VALUES($1,$2,'x.mp4',600,1,'key','uploaded',$3,$3)", "v" + suffix, "p" + suffix, now)

            async def reserve(video_id: str) -> bool:
                connection = await asyncpg.connect(POSTGRES_TEST_URL, server_settings={"search_path": schema_name})
                try:
                    await connection.execute("UPDATE videos SET status='validated' WHERE id=$1", video_id)
                    return True
                except asyncpg.PostgresError:
                    return False
                finally:
                    await connection.close()

            results = await asyncio.gather(reserve("v1"), reserve("v2"))
            assert sorted(results) == [False, True]
            assert await admin.fetchval("SELECT count(*) FROM usage_reservations WHERE status='reserved'") == 1
        finally:
            await admin.execute("SET search_path TO public")
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            await admin.close()

    asyncio.run(scenario())


def test_postgres_export_reservation_releases_on_failure_and_finalizes_on_ready() -> None:
    async def scenario() -> None:
        import asyncpg

        schema_name = "ck_export_" + uuid.uuid4().hex[:12]
        admin = await asyncpg.connect(POSTGRES_TEST_URL)
        try:
            await admin.execute(f'CREATE SCHEMA "{schema_name}"')
            await admin.execute(f'SET search_path TO "{schema_name}"')
            await admin.execute(_migration_schema())
            now = "2026-08-22T00:00:00+00:00"
            later = "2026-08-23T00:00:00+00:00"
            await admin.execute(
                "INSERT INTO users(id,name,email,password_hash,created_at,updated_at) VALUES('u','User','u@example.test','hash',$1,$1)",
                now,
            )
            await admin.execute(
                "INSERT INTO projects(id,user_id,title,status,created_at,updated_at,stage) VALUES('p','u','p','ready',$1,$1,'ready')",
                now,
            )
            await admin.execute(
                "INSERT INTO videos(id,project_id,original_filename,duration,file_size,file_path,status,created_at,expires_at) VALUES('v','p','x.mp4',60,1,'key','ready',$1,$2)",
                now,
                later,
            )
            await admin.execute(
                """INSERT INTO clips(id,video_id,start_time,end_time,hook,title,reason,score,platform,status,created_at,updated_at)
                   VALUES('c','v',0,30,'hook','title','reason',90,'shorts','suggested',$1,$1)""",
                now,
            )

            async def create_export(export_id: str) -> None:
                await admin.execute(
                    """INSERT INTO exports(id,clip_id,user_id,output_path,resolution,aspect_ratio,caption_style,watermark,status,progress,error,created_at,expires_at)
                       VALUES($1,'c','u',$2,'720p','9:16','kinetic',1,'queued',0,NULL,$3,$4)""",
                    export_id,
                    f"users/u/exports/{export_id}/clip.mp4",
                    now,
                    later,
                )

            await create_export("e-failed")
            assert await admin.fetchval("SELECT exports_used FROM usage WHERE user_id='u'") == 1
            assert await admin.fetchval(
                "SELECT status FROM usage_reservations WHERE kind='export' AND resource_id='e-failed'"
            ) == "reserved"

            await admin.execute("UPDATE exports SET status='failed' WHERE id='e-failed'")
            assert await admin.fetchval("SELECT exports_used FROM usage WHERE user_id='u'") == 0
            assert await admin.fetchval(
                "SELECT status FROM usage_reservations WHERE kind='export' AND resource_id='e-failed'"
            ) == "released"

            await create_export("e-ready")
            await admin.execute("UPDATE exports SET status='ready' WHERE id='e-ready'")
            assert await admin.fetchval("SELECT exports_used FROM usage WHERE user_id='u'") == 1
            assert await admin.fetchval(
                "SELECT status FROM usage_reservations WHERE kind='export' AND resource_id='e-ready'"
            ) == "finalized"
        finally:
            await admin.execute("SET search_path TO public")
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            await admin.close()

    asyncio.run(scenario())

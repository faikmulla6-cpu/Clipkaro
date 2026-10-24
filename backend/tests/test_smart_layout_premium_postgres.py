"""Prove paid Smart Layout reservation correctness in disposable PostgreSQL.

No production data, payment integrations or external media are used.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.database import _PostgresConnection
from app.services import smart_layout_credits as quota
from app.services.smart_layout_cache import AnalysisIdentity

URL = os.environ.get("POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="Disposable POSTGRES_TEST_URL required")


def test_parallel_postgres_credit_reservations_are_exact_once_and_capped():
    async def scenario():
        import asyncpg

        uid = str(uuid.uuid4())
        project = str(uuid.uuid4())
        video = str(uuid.uuid4())
        schema = "ck_smartquota_" + uuid.uuid4().hex[:12]
        expires = (datetime.now(timezone.utc)+timedelta(days=25)).isoformat()
        admin = await asyncpg.connect(URL)
        pool = None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            await admin.execute(f'SET search_path TO "{schema}"')
            await admin.execute("""
                CREATE TABLE users (
                    id TEXT PRIMARY KEY, plan TEXT, billing_reference TEXT,
                    plan_started_at TEXT, plan_expires_at TEXT
                );
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY, user_id TEXT, project_id TEXT,
                    export_id TEXT, kind TEXT, status TEXT, progress INTEGER,
                    stage TEXT, message TEXT, error TEXT, created_at TEXT, updated_at TEXT
                );
                CREATE TABLE job_payloads (
                    job_id TEXT PRIMARY KEY,payload_json TEXT,created_at TEXT,updated_at TEXT
                );
                CREATE TABLE smart_layout_credit_periods (
                    user_id TEXT NOT NULL,period_key TEXT NOT NULL,plan_key TEXT NOT NULL,
                    allowance INTEGER NOT NULL,daily_cap INTEGER NOT NULL,
                    policy_version TEXT,period_end TEXT,created_at TEXT,
                    PRIMARY KEY(user_id,period_key)
                );
                CREATE TABLE smart_layout_credit_reservations (
                    id TEXT PRIMARY KEY,user_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,period_key TEXT NOT NULL,
                    credits INTEGER NOT NULL,status TEXT NOT NULL,
                    job_id TEXT,reserved_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    UNIQUE(user_id,fingerprint)
                );
                CREATE TABLE smart_layout_plans (
                    cache_key TEXT PRIMARY KEY,user_id TEXT,project_id TEXT,
                    clip_id TEXT,source_generation TEXT,plan_json TEXT,
                    created_at TEXT,expires_at TEXT
                );
            """)
            await admin.execute(
                "INSERT INTO users VALUES ($1,'creator','paid-sub','2026-10-20T00:00:00+00:00',$2)",
                uid,expires,
            )
            pool = await asyncpg.create_pool(
                dsn=URL,min_size=0,max_size=12,
                server_settings={"search_path":schema},
            )

            async def transaction(callback, **kwargs):
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        return await callback(_PostgresConnection(connection))

            async def fetch_one(sql,values=()):
                async with pool.acquire() as connection:
                    value = await (await _PostgresConnection(connection).execute(sql,values)).fetchone()
                    return dict(value) if value else None

            def identity(a,b):
                return AnalysisIdentity(
                    uid,project,str(uuid.uuid4()),video,"etag:same-podcast",a,b)

            with patch.object(quota,"run_in_transaction",new=transaction), \
                 patch.object(quota,"fetch_one",new=fetch_one), \
                 patch.object(quota,"get_settings",return_value=SimpleNamespace(normalized_database_backend="postgres")):
                target = identity(0.,60.)
                attempts = await asyncio.wait_for(asyncio.gather(*[
                    quota.reserve_analysis(uid,target) for _ in range(8)
                ]), timeout=30)
                assert len({v[0] for v in attempts}) == 1
                assert sorted([v[1] for v in attempts]) == ["existing"]*7+["queued"]
                assert await admin.fetchval(
                    "SELECT COALESCE(SUM(credits),0) FROM smart_layout_credit_reservations "
                    "WHERE status IN ('reserved','finalized')") == 1
                assert await admin.fetchval("SELECT COUNT(*) FROM jobs") == 1

                job_id=attempts[0][0]
                await quota.finalize_verified_plan(
                    job_id,uid,target,{"version":2,"plans":{}},source_expires_at=None,
                )
                assert await admin.fetchval(
                    "SELECT status FROM smart_layout_credit_reservations WHERE job_id=$1",
                    job_id) == "finalized"
                assert await admin.fetchval("SELECT COUNT(*) FROM smart_layout_plans") == 1
                await admin.execute("UPDATE jobs SET status='completed' WHERE id=$1",job_id)

                # More distinct clips are serialized by PostgreSQL user-row lock.
                # The plan's daily four credits cannot be exceeded by races.
                distinct = [identity((i+1)*60.,(i+2)*60.) for i in range(6)]
                results = await asyncio.wait_for(asyncio.gather(*[
                    quota.reserve_analysis(uid,item) for item in distinct
                ],return_exceptions=True),timeout=30)
                queued=[r for r in results if isinstance(r,tuple)]
                errors=[r for r in results if isinstance(r,quota.SmartLayoutQuotaError)]
                assert len(queued) == 2, (queued,errors)
                assert len(errors) == 4, errors
                assert all(r.code == "SMART_LAYOUT_CONCURRENCY" for r in errors), errors
                assert await admin.fetchval(
                    "SELECT COALESCE(SUM(credits),0) FROM smart_layout_credit_reservations "
                    "WHERE status IN ('reserved','finalized')") == 3
                for job_id,action in queued:
                    await quota.settle_analysis_job(job_id,succeeded=True)
                    await admin.execute("UPDATE jobs SET status='completed' WHERE id=$1",job_id)

                # After worker completion one daily credit remains.
                fourth,_ = await quota.reserve_analysis(uid,identity(600.,660.))
                await quota.settle_analysis_job(fourth,succeeded=True)
                await admin.execute("UPDATE jobs SET status='completed' WHERE id=$1",fourth)
                with pytest.raises(quota.SmartLayoutQuotaError,match="daily"):
                    await quota.reserve_analysis(uid,identity(720.,780.))
                assert await admin.fetchval(
                    "SELECT COALESCE(SUM(credits),0) FROM smart_layout_credit_reservations "
                    "WHERE status IN ('reserved','finalized')") == 4
        finally:
            if pool is not None:
                await pool.close()
            await admin.execute("SET search_path TO public")
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    asyncio.run(scenario())

"""Paid Smart Layout credits: isolated exact-once SQLite transaction tests."""
import asyncio
import sqlite3
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services import smart_layout_credits as quota
from app.services.billing import usage_period_key
from app.services.smart_layout_cache import AnalysisIdentity


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    async def fetchone(self):
        return self.cursor.fetchone()

    async def fetchall(self):
        return self.cursor.fetchall()


class DB:
    def __init__(self, connection):
        self.connection = connection

    async def execute(self, sql, args=()):
        return Cursor(self.connection.execute(sql, args))


class PremiumSmartLayoutCreditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(
                id TEXT PRIMARY KEY, plan TEXT, billing_reference TEXT,
                plan_started_at TEXT, plan_expires_at TEXT
            );
            CREATE TABLE jobs(
                id TEXT PRIMARY KEY, user_id TEXT, project_id TEXT,
                export_id TEXT, kind TEXT, status TEXT,
                progress INTEGER, stage TEXT, message TEXT, error TEXT,
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE job_payloads(
                job_id TEXT PRIMARY KEY, payload_json TEXT,
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE smart_layout_credit_periods(
                user_id TEXT, period_key TEXT, plan_key TEXT,
                allowance INTEGER, daily_cap INTEGER, policy_version TEXT,
                period_end TEXT, created_at TEXT, PRIMARY KEY(user_id,period_key)
            );
            CREATE TABLE smart_layout_credit_reservations(
                id TEXT PRIMARY KEY, user_id TEXT, fingerprint TEXT,
                period_key TEXT, credits INTEGER,
                status TEXT CHECK(status IN ('reserved','finalized','released')),
                job_id TEXT, reserved_at TEXT, updated_at TEXT,
                UNIQUE(user_id,fingerprint)
            );
        """)
        self.lock = asyncio.Lock()
        self.uid = str(uuid.uuid4())
        self.pid = str(uuid.uuid4())
        self.vid = str(uuid.uuid4())
        self.started = "2026-10-20T00:00:00+00:00"
        self.expires = (datetime.now(timezone.utc) + timedelta(days=35)).isoformat()
        self.conn.execute(
            "INSERT INTO users VALUES (?,?,?,?,?)",
            (self.uid,"creator","sub_paid",self.started,self.expires))
        self.stack = []
        for patcher in (
            patch.object(quota,"get_settings",return_value=SimpleNamespace(normalized_database_backend="sqlite")),
            patch.object(quota,"run_in_transaction",side_effect=self.transaction),
            patch.object(quota,"fetch_one",side_effect=self.fetch_one),
        ):
            patcher.start()
            self.stack.append(patcher)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for patcher in reversed(self.stack):
            patcher.stop()
        self.conn.close()

    async def transaction(self, callback, **kwargs):
        async with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                result = await callback(DB(self.conn))
                self.conn.commit()
                return result
            except Exception:
                self.conn.rollback()
                raise

    async def fetch_one(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def identity(self, a=0., b=60., clip=None):
        return AnalysisIdentity(
            self.uid,self.pid,clip or str(uuid.uuid4()),
            self.vid,"etag:test-original",a,b,
        )

    def used(self):
        return self.conn.execute(
            "SELECT COALESCE(SUM(credits),0) FROM smart_layout_credit_reservations WHERE status IN ('reserved','finalized')"
        ).fetchone()[0]

    async def test_exact_minute_cost_boundaries_and_invalid_media(self):
        for duration, expected in ((.1,1),(59.9999,1),(60.,1),(60.0001,2),
                                   (119.9999,2),(120.,2),(120.0001,3),(180.,3)):
            self.assertEqual(quota.credit_cost(duration),expected)
        for bad in (0,180.001,float("nan"),float("inf"),-1):
            with self.assertRaises(quota.SmartLayoutQuotaError):
                quota.credit_cost(bad)

    async def test_simultaneous_identical_requests_are_only_charged_once(self):
        identity = self.identity()
        a,b = await asyncio.gather(
            quota.reserve_analysis(self.uid,identity),
            quota.reserve_analysis(self.uid,identity))
        self.assertEqual(a[0],b[0])
        self.assertEqual({a[1],b[1]},{"queued","existing"})
        self.assertEqual(self.used(),1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],1)
        await quota.settle_analysis_job(a[0],succeeded=True)
        await quota.settle_analysis_job(a[0],succeeded=True)
        state = await quota.entitlement_status({"id":self.uid},rollout=True)
        self.assertEqual((state["remaining"],state["daily_remaining"]),(11,3))

    async def test_failure_refunds_once_and_retry_reserves_once(self):
        identity=self.identity()
        first,_ = await quota.reserve_analysis(self.uid,identity)
        await quota.settle_analysis_job(first,succeeded=False)
        await quota.settle_analysis_job(first,succeeded=False)
        self.assertEqual(self.used(),0)
        second,_ = await quota.reserve_analysis(self.uid,identity)
        self.assertNotEqual(first,second)
        self.assertEqual(self.used(),1)
        await quota.settle_analysis_job(second,succeeded=True)
        self.assertEqual(self.used(),1)

    async def test_rolling_daily_limit_blocks_fifth_creator_credit(self):
        for _ in range(4):
            job,_ = await quota.reserve_analysis(self.uid,self.identity())
            await quota.settle_analysis_job(job,succeeded=True)
        self.assertEqual(self.used(),4)
        with self.assertRaises(quota.SmartLayoutQuotaError) as error:
            await quota.reserve_analysis(self.uid,self.identity())
        self.assertEqual(error.exception.code,"SMART_LAYOUT_DAILY")
        self.assertEqual(self.used(),4)

    async def test_monthly_credit_shortage_blocks_two_credit_clip(self):
        period=usage_period_key(dict(self.conn.execute("SELECT * FROM users").fetchone()))
        self.conn.execute(
            "INSERT INTO smart_layout_credit_reservations VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()),self.uid,"1"*64,period,11,"finalized","old-job",
             datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
        with self.assertRaises(quota.SmartLayoutQuotaError) as error:
            await quota.reserve_analysis(self.uid,self.identity(0.,120.))
        self.assertEqual(error.exception.code,"SMART_LAYOUT_CREDITS")

    async def test_same_cycle_upgrade_carries_usage(self):
        first,_=await quota.reserve_analysis(self.uid,self.identity())
        await quota.settle_analysis_job(first,succeeded=True)
        old=usage_period_key(dict(self.conn.execute("SELECT * FROM users").fetchone()))
        self.conn.execute("UPDATE users SET plan='growth' WHERE id=?",(self.uid,))
        new=usage_period_key(dict(self.conn.execute("SELECT * FROM users").fetchone()))
        async def migrate(db):
            await quota.migrate_smart_layout_period(db,self.uid,old,new,"growth")
        await self.transaction(migrate)
        balance=await quota.entitlement_status({"id":self.uid},rollout=True)
        self.assertEqual((balance["allowance"],balance["remaining"]),(40,39))
        self.assertEqual(balance["daily_remaining"],9)

    async def test_cached_model_reanalysis_does_not_charge_next_cycle(self):
        identity=self.identity()
        first,_=await quota.reserve_analysis(self.uid,identity)
        await quota.settle_analysis_job(first,succeeded=True)
        old=usage_period_key(dict(self.conn.execute("SELECT * FROM users").fetchone()))
        self.conn.execute(
            "UPDATE users SET plan_started_at='2026-11-20T00:00:00+00:00' WHERE id=?",
            (self.uid,))
        second,status=await quota.reserve_analysis(self.uid,identity)
        self.assertEqual(status,"queued")
        self.assertNotEqual(first,second)
        self.assertEqual(self.used(),1)
        credit=self.conn.execute(
            "SELECT period_key,status FROM smart_layout_credit_reservations WHERE user_id=?",
            (self.uid,)).fetchone()
        self.assertEqual(credit["period_key"],old)
        self.assertEqual(credit["status"],"finalized")
        await quota.settle_analysis_job(second,succeeded=True)
        new_balance=await quota.entitlement_status({"id":self.uid},rollout=True)
        self.assertEqual(new_balance["remaining"],12)

    async def test_free_is_denied_without_side_effects(self):
        self.conn.execute("UPDATE users SET plan='free',plan_expires_at=NULL WHERE id=?",(self.uid,))
        with self.assertRaises(quota.SmartLayoutQuotaError) as error:
            await quota.reserve_analysis(self.uid,self.identity())
        self.assertEqual(error.exception.code,"SMART_LAYOUT_UPGRADE")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],0)
        self.assertEqual(self.used(),0)

    async def test_source_generation_is_billing_fingerprint_not_model_revision(self):
        identity=self.identity()
        first=quota.analysis_fingerprint(identity)
        self.assertEqual(first,quota.analysis_fingerprint(identity))
        changed=AnalysisIdentity(identity.user_id,identity.project_id,identity.clip_id,
                                 identity.video_id,"etag:another",identity.start,identity.end)
        self.assertNotEqual(first,quota.analysis_fingerprint(changed))


if __name__ == "__main__":
    unittest.main()

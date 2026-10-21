"""Reproduce simultaneous captured-payment callbacks against real PostgreSQL.

Runs only with an isolated disposable POSTGRES_TEST_URL (GitHub Actions Postgres).
No Razorpay access and no production database credentials are used.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import patch

import pytest

from app.api.credit_topups import credit_checkout
from app.core.database import _PostgresConnection

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Disposable POSTGRES_TEST_URL is required")


def test_concurrent_credit_claim_is_exact_once_even_with_two_stale_reads():
    async def scenario():
        import asyncpg

        schema = "ck_credit_" + uuid.uuid4().hex[:12]
        admin = await asyncpg.connect(POSTGRES_TEST_URL)
        pool = None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            await admin.execute(f'SET search_path TO "{schema}"')
            await admin.execute("""
                CREATE TABLE credit_topup_checkouts (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    minutes INTEGER NOT NULL, shorts INTEGER NOT NULL,
                    status TEXT NOT NULL, payment_id TEXT, verified_at TEXT
                );
                CREATE TABLE credit_topup_wallets (
                    user_id TEXT PRIMARY KEY, minutes_balance DOUBLE PRECISION NOT NULL,
                    shorts_balance INTEGER NOT NULL, updated_at TEXT NOT NULL
                );
            """)
            await admin.execute(
                "INSERT INTO credit_topup_checkouts(id,user_id,minutes,shorts,status) "
                "VALUES('same-order','test-user',10,2,'created')"
            )
            await admin.execute(
                "INSERT INTO credit_topup_wallets(user_id,minutes_balance,shorts_balance,updated_at) "
                "VALUES('test-user',0,0,'before')"
            )
            pool = await asyncpg.create_pool(
                dsn=POSTGRES_TEST_URL, min_size=0, max_size=3,
                server_settings={"search_path": schema},
            )
            both_read = asyncio.Event()
            reads = 0

            class CoordinatedConnection(_PostgresConnection):
                async def execute(self, query, params=()):
                    nonlocal reads
                    cur = await super().execute(query, params)
                    if query.strip().startswith("SELECT * FROM credit_topup_checkouts"):
                        reads += 1
                        if reads == 2:
                            both_read.set()
                        # Both transactions read the old 'created' status.
                        # This reproduces the exact stale-read double-credit race.
                        await asyncio.wait_for(both_read.wait(), timeout=10)
                    return cur

            async def transactional(operation, *, mode="IMMEDIATE", operation_name="transaction"):
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        return await operation(CoordinatedConnection(connection))

            # Bypass the optional advisory lock deliberately: even older backend
            # instances or duplicate event deliveries cannot double-settle.
            with patch("app.api.credit_topups.run_in_transaction", new=transactional):
                settled = await asyncio.wait_for(asyncio.gather(
                    credit_checkout("same-order", "payment_1"),
                    credit_checkout("same-order", "payment_1"),
                ), timeout=20)
            assert reads == 2
            assert sorted(result[0] for result in settled) == [False, True]
            assert await admin.fetchval(
                "SELECT minutes_balance FROM credit_topup_wallets WHERE user_id='test-user'"
            ) == 10
            assert await admin.fetchval(
                "SELECT shorts_balance FROM credit_topup_wallets WHERE user_id='test-user'"
            ) == 2
            assert await admin.fetchval(
                "SELECT status FROM credit_topup_checkouts WHERE id='same-order'"
            ) == "verified"
            assert await admin.fetchval(
                "SELECT COUNT(*) FROM credit_topup_checkouts WHERE status='verified'"
            ) == 1

            # If a wallet write fails, the checkout claim must roll back too.
            await admin.execute(
                "INSERT INTO credit_topup_checkouts(id,user_id,minutes,shorts,status) "
                "VALUES('retry-after-error','test-user',5,1,'created')"
            )

            class FailingWalletConnection(_PostgresConnection):
                async def execute(self, query, params=()):
                    if "UPDATE credit_topup_wallets" in query:
                        raise RuntimeError("Injected wallet failure")
                    return await super().execute(query, params)

            async def failed_transaction(operation, *, mode="IMMEDIATE", operation_name="transaction"):
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        return await operation(FailingWalletConnection(connection))

            with patch("app.api.credit_topups.run_in_transaction", new=failed_transaction):
                with pytest.raises(RuntimeError, match="Injected wallet failure"):
                    await credit_checkout("retry-after-error", "payment_2")
            assert await admin.fetchval(
                "SELECT status FROM credit_topup_checkouts WHERE id='retry-after-error'"
            ) == "created"
            assert await admin.fetchval(
                "SELECT minutes_balance FROM credit_topup_wallets WHERE user_id='test-user'"
            ) == 10

            async def retry_transaction(operation, *, mode="IMMEDIATE", operation_name="transaction"):
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        return await operation(_PostgresConnection(connection))

            with patch("app.api.credit_topups.run_in_transaction", new=retry_transaction):
                assert await credit_checkout("retry-after-error", "payment_2") == (True, 15.0, 3)
                assert await credit_checkout("retry-after-error", "payment_2") == (False, 15.0, 3)
        finally:
            if pool is not None:
                await pool.close()
            await admin.execute("SET search_path TO public")
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    asyncio.run(scenario())

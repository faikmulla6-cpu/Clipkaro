import asyncio
import sqlite3
import threading

import aiosqlite
import pytest

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one, init_db, run_in_transaction


@pytest.fixture()
def hardened_sqlite(tmp_path):
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "sqlite_busy_timeout_ms": settings.sqlite_busy_timeout_ms,
        "sqlite_lock_max_attempts": settings.sqlite_lock_max_attempts,
        "sqlite_lock_retry_base_ms": settings.sqlite_lock_retry_base_ms,
    }
    settings.database_path = tmp_path / "sqlite-contention.db"
    settings.storage_root = tmp_path / "storage"
    # Keep contention tests fast while forcing at least one retry.
    settings.sqlite_busy_timeout_ms = 20
    settings.sqlite_lock_max_attempts = 8
    settings.sqlite_lock_retry_base_ms = 5
    asyncio.run(init_db())
    try:
        yield settings
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


async def _close_raw_test_connection(db: aiosqlite.Connection) -> None:
    """Test-owned connections must not leak their worker threads either."""
    await db.close()
    worker = getattr(db, "_thread", db)
    is_alive = getattr(worker, "is_alive", None)
    join = getattr(worker, "join", None)
    if callable(is_alive) and callable(join) and is_alive():
        await asyncio.to_thread(join, 1.0)
    if callable(is_alive):
        assert not is_alive()


def test_every_connection_uses_busy_timeout_and_wal(hardened_sqlite):
    busy = asyncio.run(fetch_one("PRAGMA busy_timeout"))
    journal = asyncio.run(fetch_one("PRAGMA journal_mode"))
    synchronous = asyncio.run(fetch_one("PRAGMA synchronous"))

    assert busy and next(iter(busy.values())) == hardened_sqlite.sqlite_busy_timeout_ms
    assert journal and str(next(iter(journal.values()))).lower() == "wal"
    # SQLite reports NORMAL as integer 1.
    assert synchronous and int(next(iter(synchronous.values()))) == 1


def test_short_lived_event_loops_leave_no_aiosqlite_workers(hardened_sqlite):
    baseline = {id(thread) for thread in threading.enumerate() if isinstance(thread, aiosqlite.Connection)}

    for _ in range(12):
        assert asyncio.run(fetch_one("SELECT 1 AS value")) == {"value": 1}

    remaining = {id(thread) for thread in threading.enumerate() if isinstance(thread, aiosqlite.Connection)}
    assert remaining == baseline


def test_locked_write_retries_then_commits_once(hardened_sqlite):
    async def scenario():
        locker = await aiosqlite.connect(hardened_sqlite.database_path, timeout=0.01)
        await locker.execute("PRAGMA busy_timeout = 5")
        await locker.execute("BEGIN IMMEDIATE")
        await locker.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            ("lock-holder", None, "test.lock_holder", "", "", "{}", "2026-08-08T00:00:00+00:00"),
        )
        try:
            writer = asyncio.create_task(execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
                ("retried-write", None, "test.retried", "", "", "{}", "2026-08-08T00:00:01+00:00"),
            ))
            # Longer than one configured busy_timeout, so the writer must see a
            # real SQLITE_BUSY before the lock becomes available.
            await asyncio.sleep(0.06)
            await locker.commit()
            await writer
        finally:
            await _close_raw_test_connection(locker)

        rows = await fetch_all("SELECT id FROM audit_events WHERE id='retried-write'")
        return rows

    assert asyncio.run(scenario()) == [{"id": "retried-write"}]


def test_retry_exhaustion_surfaces_lock_without_partial_write(hardened_sqlite):
    hardened_sqlite.sqlite_busy_timeout_ms = 5
    hardened_sqlite.sqlite_lock_max_attempts = 2
    hardened_sqlite.sqlite_lock_retry_base_ms = 1

    async def scenario():
        locker = await aiosqlite.connect(hardened_sqlite.database_path, timeout=0.01)
        await locker.execute("PRAGMA busy_timeout = 5")
        await locker.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                await execute(
                    "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
                    ("must-not-commit", None, "test.exhausted", "", "", "{}", "2026-08-08T00:00:02+00:00"),
                )
        finally:
            await locker.rollback()
            await _close_raw_test_connection(locker)

        return await fetch_one("SELECT id FROM audit_events WHERE id='must-not-commit'")

    assert asyncio.run(scenario()) is None


def test_transaction_retry_rolls_back_the_entire_failed_attempt(hardened_sqlite):
    asyncio.run(execute("CREATE TABLE retry_counter(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"))
    asyncio.run(execute("INSERT INTO retry_counter(id,value) VALUES (1,0)"))
    attempts = 0

    async def transaction(db):
        nonlocal attempts
        attempts += 1
        await db.execute("UPDATE retry_counter SET value=value+1 WHERE id=1")
        if attempts == 1:
            # Simulate a lock appearing after business work has started. The
            # transaction helper must roll this increment back before retrying.
            raise sqlite3.OperationalError("database is locked")

    asyncio.run(run_in_transaction(
        transaction,
        mode="IMMEDIATE",
        operation_name="rollback retry test",
    ))
    row = asyncio.run(fetch_one("SELECT value FROM retry_counter WHERE id=1"))

    assert attempts == 2
    assert row == {"value": 1}


def test_many_concurrent_writers_do_not_lose_updates(hardened_sqlite):
    hardened_sqlite.sqlite_busy_timeout_ms = 50
    hardened_sqlite.sqlite_lock_max_attempts = 12
    asyncio.run(execute("CREATE TABLE write_counter(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"))
    asyncio.run(execute("INSERT INTO write_counter(id,value) VALUES (1,0)"))

    async def compete():
        await asyncio.gather(*(
            execute("UPDATE write_counter SET value=value+1 WHERE id=1")
            for _ in range(24)
        ))
        return await fetch_one("SELECT value FROM write_counter WHERE id=1")

    assert asyncio.run(compete()) == {"value": 24}


def test_karo_minute_reservation_remains_exactly_once_after_lock_retry(hardened_sqlite):
    now = "2026-08-08T00:00:00+00:00"
    expires = "2026-08-09T00:00:00+00:00"
    asyncio.run(execute(
        """INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at)
           VALUES (?,?,?,?, 'free','creator',1,?,?)""",
        ("lock-user", "Lock User", "lock@example.com", "hash", now, now),
    ))
    asyncio.run(execute(
        "INSERT INTO projects(id,user_id,title,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
        ("lock-project", "lock-user", "Locked quota", "processing", now, now),
    ))
    asyncio.run(execute(
        """INSERT INTO videos(id,project_id,original_filename,duration,width,height,file_size,file_path,status,created_at,expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        ("lock-video", "lock-project", "locked.mp4", 0.0, 0, 0, 1, "/tmp/locked.mp4", "uploaded", now, expires),
    ))

    async def scenario():
        locker = await aiosqlite.connect(hardened_sqlite.database_path, timeout=0.01)
        await locker.execute("PRAGMA busy_timeout = 5")
        await locker.execute("BEGIN IMMEDIATE")
        try:
            reservation = asyncio.create_task(execute(
                "UPDATE videos SET duration=?,width=?,height=?,status='validated' WHERE id=?",
                (600.0, 1920, 1080, "lock-video"),
            ))
            await asyncio.sleep(0.06)
            await locker.commit()
            await reservation
        finally:
            await _close_raw_test_connection(locker)

        # Retrying the same validated state must not create a second reservation.
        await execute(
            "UPDATE videos SET duration=?,width=?,height=?,status='validated' WHERE id=?",
            (600.0, 1920, 1080, "lock-video"),
        )
        usage = await fetch_one("SELECT source_minutes FROM usage WHERE user_id='lock-user'")
        reservations = await fetch_all(
            "SELECT amount,status FROM usage_reservations WHERE user_id='lock-user' AND kind='minutes'"
        )
        return usage, reservations

    usage, reservations = asyncio.run(scenario())
    assert usage == {"source_minutes": 10.0}
    assert reservations == [{"amount": 10.0, "status": "reserved"}]

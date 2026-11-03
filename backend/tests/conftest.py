"""Shared pytest configuration.

Billing routes now have a single canonical owner in ``app.api.billing_lifecycle``.
Tests patch that module directly; no legacy route bridge is intentionally kept.
"""

from __future__ import annotations

import pytest

from app.core import database as database_module


def _terminate_cached_postgres_pool() -> None:
    """Keep asyncpg pools from leaking across pytest event loops.

    Several regression tests intentionally use ``asyncio.run(...)``. Each call
    creates a fresh event loop, while the application's PostgreSQL pool is a
    process-global cache. Reusing that pool from a later loop is invalid in
    asyncpg and can surface as ``InterfaceError: another operation is in
    progress`` or ``ConnectionDoesNotExistError`` even though PostgreSQL itself
    is healthy.

    Production is unaffected because this helper exists only in the test suite.
    PostgreSQL integration coverage still runs against the real CI service; this
    fixture only guarantees that every test gets a pool bound to its own loop.
    """
    pool = database_module._postgres_pool
    if pool is None:
        return
    try:
        # asyncpg.Pool.terminate() is synchronous and is safe here even when the
        # loop that originally owned the pool has already been closed.
        pool.terminate()
    finally:
        database_module._postgres_pool = None


@pytest.fixture(autouse=True)
def isolate_cached_postgres_pool_between_tests():
    _terminate_cached_postgres_pool()
    try:
        yield
    finally:
        _terminate_cached_postgres_pool()

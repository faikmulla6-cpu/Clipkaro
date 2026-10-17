"""Source availability: transient storage errors must never mean expired."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from app.api.worker_jobs import _require_source_available, _source_available, _source_state


class SourceAvailabilityStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = patch(
            "app.api.worker_jobs.get_settings",
            return_value=SimpleNamespace(normalized_storage_backend="gcs"),
        )
        self.key = patch(
            "app.api.worker_jobs.validate_object_key",
            return_value="users/user1/projects/proj/source.mp4",
        )
        self.settings.start()
        self.key.start()
        self.addCleanup(self.settings.stop)
        self.addCleanup(self.key.stop)

    async def state(self, result=None, error=None):
        stat = AsyncMock(side_effect=error) if error else AsyncMock(return_value=result)
        storage = SimpleNamespace(stat=stat)
        with patch("app.api.worker_jobs.get_storage_provider", return_value=storage):
            state = await _source_state(
                {"status": "ready", "file_path": "users/user1/projects/proj/source.mp4",
                 "object_generation": "etag:abc"}, "user1",
            )
        return state, stat.await_count

    async def test_present_source(self):
        state, attempts = await self.state(SimpleNamespace(generation="etag:abc"))
        self.assertEqual(state, "available")
        self.assertEqual(attempts, 1)

    async def test_deleted_source_is_missing_not_timeout(self):
        state, _ = await self.state(None)
        self.assertEqual(state, "missing")

    async def test_transient_storage_failures_are_unverified(self):
        state, attempts = await self.state(error=TimeoutError("temporary network timeout"))
        self.assertEqual(state, "unverified")
        self.assertEqual(attempts, 2)

    async def test_stale_object_generation_is_not_trusted(self):
        state, _ = await self.state(SimpleNamespace(generation="etag:different"))
        self.assertEqual(state, "unverified")

    async def test_explicit_retention_expiry(self):
        self.assertEqual(await _source_state({"status": "expired"}, "user1"), "expired")

    async def test_unverified_remains_closed_for_export(self):
        storage = SimpleNamespace(stat=AsyncMock(side_effect=TimeoutError("offline")))
        with patch("app.api.worker_jobs.get_storage_provider", return_value=storage):
            self.assertFalse(await _source_available(
                {"status": "ready", "file_path": "users/user1/projects/proj/source.mp4"}, "user1"
            ))


    async def test_storage_error_is_retryable_http_503(self):
        with patch("app.api.worker_jobs._source_state", new_callable=AsyncMock, return_value="unverified"):
            with self.assertRaises(HTTPException) as caught:
                await _require_source_available({"status": "ready"}, "user1")
        self.assertEqual(caught.exception.status_code, 503)

    async def test_genuinely_missing_source_is_http_410(self):
        with patch("app.api.worker_jobs._source_state", new_callable=AsyncMock, return_value="missing"):
            with self.assertRaises(HTTPException) as caught:
                await _require_source_available({"status": "expired"}, "user1")
        self.assertEqual(caught.exception.status_code, 410)


if __name__ == "__main__":
    unittest.main()

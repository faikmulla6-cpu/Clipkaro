"""Isolated API security regressions: mock DB/Backblaze; no credentials."""
import io
import json
import os
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request
from app.api import smart_layout_v2 as api
from app.services.smart_layout_cache import AnalysisIdentity, private_plan_key


def user_ids():
    return [str(uuid.uuid4()) for _ in range(4)]


class SmartLayoutSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_feature_off_is_inaccessible(self):
        with patch.dict(os.environ,{"KARO_REAL_PREVIEW_ENABLED":"false"}):
            with self.assertRaises(HTTPException) as exc:
                await api.analysis_status(str(uuid.uuid4()),{"id":str(uuid.uuid4())})
            self.assertEqual(exc.exception.status_code,404)

    async def test_authorized_clip_query_enforces_owner_and_blocks_cross_tenant(self):
        clip,user=user_ids()[:2]
        with patch.object(api,"fetch_one",new_callable=AsyncMock,return_value=None) as query:
            with self.assertRaises(HTTPException) as exc:
                await api._owned(clip,user)
            self.assertEqual(exc.exception.status_code,404)
            sql,params=query.call_args.args
            self.assertIn("p.user_id=?",sql)
            self.assertEqual(params,(clip,user))

    async def test_superseded_or_expired_source_is_refused(self):
        clip,user=user_ids()[:2]
        data={"clip_status":"ready","source_status":"ready","expires_at":"2000-01-01T00:00:00+00:00"}
        with patch.object(api,"fetch_one",new_callable=AsyncMock,return_value=data):
            with self.assertRaises(HTTPException) as exc:
                await api._owned(clip,user)
            self.assertEqual(exc.exception.status_code,410)
        data.update(clip_status="superseded")
        with patch.object(api,"fetch_one",new_callable=AsyncMock,return_value=data):
            with self.assertRaises(HTTPException) as exc:
                await api._owned(clip,user)
            self.assertEqual(exc.exception.status_code,409)

    async def test_malformed_database_cache_never_returned_or_marked_ready(self):
        uid,pid,cid,vid=user_ids()
        identity=AnalysisIdentity(uid,pid,cid,vid,"etag:xyz",0.,2.)
        payload={"version":2,"cache_key":private_plan_key(identity),
                 "plans":{"auto":{"scenes":["../../etc"]}}}
        with patch("app.services.smart_layout_repository.read_plan",
                   new_callable=AsyncMock,return_value=payload):
            status=await api._cached({"source_width":1280,"source_height":720},identity)
        self.assertIsNone(status)

    async def test_private_mp4_byte_range_and_no_url_redirect(self):
        uid,pid,cid,vid=user_ids()
        key=f"users/{uid}/projects/{pid}/videos/{vid}/source.mp4"
        source=b"private-authorized-video"
        class FakeS3:
            bucket="hidden"
            client=MagicMock()
            async def stat(self,k):return SimpleNamespace(size=len(source),generation="etag:abc")
            @staticmethod
            def _generation(response):return "etag:" + str(response.get("ETag","")).strip('"')
        fake=FakeS3()
        fake.client.get_object.side_effect=lambda **kw:{
            "ETag":'"abc"',
            "Body":io.BytesIO(source[int(kw["Range"].split("=")[1].split("-")[0]):int(kw["Range"].split("-")[-1])+1])
        }
        scope={"type":"http","method":"GET","path":"/v1/test",
               "headers":[(b"range",b"bytes=2-9")]}
        req=Request(scope)
        owned={"original_filename":"a.mp4","file_path":key,"object_generation":"etag:abc"}
        with patch.object(api,"enabled_for_user",return_value=True), \
             patch.object(api,"_owned",new_callable=AsyncMock,return_value=owned), \
             patch.object(api,"get_storage_provider",return_value=fake), \
             patch.object(api,"S3StorageProvider",FakeS3), \
             patch.object(api,"get_settings",return_value=SimpleNamespace(normalized_storage_backend="gcs")), \
             patch.object(api,"consume_rate_limit",new_callable=AsyncMock,return_value=True):
            res=await api.original_canvas_video(cid,req,{"id":uid})
            body=b"".join([part async for part in res.body_iterator])
        self.assertEqual(res.status_code,206)
        self.assertEqual(res.headers["Content-Range"],f"bytes 2-9/{len(source)}")
        self.assertNotIn("location",res.headers)
        self.assertEqual(body,source[2:10])
        self.assertEqual(fake.client.get_object.call_args.kwargs["Key"],key)
        self.assertEqual(fake.client.get_object.call_args.kwargs["IfMatch"],'"abc"')

    async def test_cross_generation_media_fails_closed(self):
        uid,pid,cid,vid=user_ids()
        key=f"users/{uid}/projects/{pid}/videos/{vid}/source.mp4"
        class FakeS3:
            bucket="hidden"
            async def stat(self,k):return SimpleNamespace(size=777,generation="etag:new")
        row={"original_filename":"a.mp4","file_path":key,"object_generation":"etag:old"}
        req=Request({"type":"http","method":"GET","path":"/v1/test","headers":[]})
        with patch.object(api,"enabled_for_user",return_value=True), \
             patch.object(api,"_owned",new_callable=AsyncMock,return_value=row), \
             patch.object(api,"get_storage_provider",return_value=FakeS3()), \
             patch.object(api,"S3StorageProvider",FakeS3), \
             patch.object(api,"get_settings",return_value=SimpleNamespace(normalized_storage_backend="gcs")):
            with self.assertRaises(HTTPException) as exc:
                await api.original_canvas_video(cid,req,{"id":uid})
        self.assertEqual(exc.exception.status_code,409)


if __name__=="__main__":
    unittest.main()


class PrivateSourceRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_swap_between_head_and_get_is_rejected(self):
        uid,pid,cid,vid=user_ids()
        key=f"users/{uid}/projects/{pid}/videos/{vid}/original.mp4"
        stale=io.BytesIO(b"replacement media must never reach preview")
        class FakeS3:
            bucket="private"
            client=MagicMock()
            async def stat(self,k):return SimpleNamespace(size=200,generation="etag:approved")
            @staticmethod
            def _generation(response):
                return "etag:"+str(response.get("ETag","")).strip('"')
        obj=FakeS3()
        obj.client.get_object.return_value={"ETag":'"replaced"',"Body":stale}
        row={"original_filename":"original.mp4","file_path":key,"object_generation":"etag:approved"}
        req=Request({"type":"http","method":"GET",
                     "path":"/api/v1/source","headers":[(b"range",b"bytes=0-99")]})
        with patch.object(api,"enabled_for_user",return_value=True), \
             patch.object(api,"_owned",new_callable=AsyncMock,return_value=row), \
             patch.object(api,"get_storage_provider",return_value=obj), \
             patch.object(api,"S3StorageProvider",FakeS3), \
             patch.object(api,"get_settings",return_value=SimpleNamespace(normalized_storage_backend="gcs")), \
             patch.object(api,"consume_rate_limit",new_callable=AsyncMock,return_value=True):
            with self.assertRaises(HTTPException) as exc:
                await api.original_canvas_video(cid,req,{"id":uid})
        self.assertEqual(exc.exception.status_code,409)
        self.assertTrue(stale.closed)
        self.assertEqual(obj.client.get_object.call_args.kwargs["IfMatch"],'"approved"')


class VerifiedB2DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_analysis_download_checks_b2_etag_and_never_uses_latest_unchecked(self):
        from app.services import smart_layout_job as job
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            class FakeS3:
                bucket = "private"
                def __init__(self, etag):
                    self.client = MagicMock()
                    self.client.get_object.return_value = {
                        "ETag": '"' + etag + '"',
                        "Body": io.BytesIO(b"A" * 1500),
                    }
            fake = FakeS3("approved")
            with patch.object(job, "S3StorageProvider", FakeS3):
                target = Path(folder) / "source.mp4"
                await job._download_verified_source(fake,"users/owner/source.mp4",target,"etag:approved")
                self.assertEqual(target.stat().st_size,1500)
                self.assertEqual(fake.client.get_object.call_args.kwargs["IfMatch"],'"approved"')
                target.unlink()
                swapped = FakeS3("replaced")
                with self.assertRaises(RuntimeError):
                    await job._download_verified_source(swapped,"users/owner/source.mp4",target,"etag:approved")
                self.assertFalse(target.exists())

    async def test_analysis_download_version_id_is_exact(self):
        from app.services import smart_layout_job as job
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            class FakeS3:
                bucket = "private"
                def __init__(self):
                    self.client = MagicMock()
                    self.client.get_object.return_value = {
                        "VersionId":"fixed-version",
                        "ETag":'"any-etag"',
                        "Body":io.BytesIO(b"B" * 1500),
                    }
            storage = FakeS3()
            target = Path(folder) / "video.mp4"
            with patch.object(job,"S3StorageProvider",FakeS3):
                await job._download_verified_source(storage,"users/owner/video.mp4",target,
                                                    "version:fixed-version")
            self.assertEqual(storage.client.get_object.call_args.kwargs["VersionId"],"fixed-version")
            self.assertEqual(target.stat().st_size,1500)


class SmartLayoutCanaryGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_canary_defaults_off_and_requires_explicit_allowlist(self):
        owner = str(uuid.uuid4())
        stranger = str(uuid.uuid4())
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"true",
                                     "KARO_REAL_PREVIEW_CANARY_USERS":""}):
            self.assertFalse(api.enabled_for_user(owner))
            self.assertFalse((await api.preview_capabilities({"id":owner}))["available"])
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"true",
                                     "KARO_REAL_PREVIEW_CANARY_USERS":owner}):
            self.assertTrue(api.enabled_for_user(owner))
            self.assertFalse(api.enabled_for_user(stranger))
            self.assertTrue((await api.preview_capabilities({"id":owner}))["available"])
            self.assertFalse((await api.preview_capabilities({"id":stranger}))["available"])
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"false",
                                     "KARO_REAL_PREVIEW_CANARY_USERS":"*"}):
            self.assertFalse(api.enabled_for_user(owner))

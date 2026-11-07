"""Isolated API security regressions: mock DB/Backblaze; no credentials."""
import io
import json
import os
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request
from app.api import smart_layout_v2 as api
from app.services.smart_layout_cache import AnalysisIdentity, private_plan_key


def user_ids():
    return [str(uuid.uuid4()) for _ in range(4)]


class SmartLayoutSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_paid_beta_off_is_inaccessible(self):
        with patch.dict(os.environ,{"KARO_REAL_PREVIEW_ENABLED":"false",
                                    "KARO_REAL_PREVIEW_FREE_TRIAL_ENABLED":"true"}), \
             patch.object(api, "entitlement_status", new_callable=AsyncMock,
                          return_value={"enabled":True,"plan":"creator","remaining":12}):
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

    async def test_updated_live_face_model_invalidates_prior_cached_plans(self):
        from app.services.smart_layout_cache import (
            AnalysisIdentity, MODEL_VERSION, private_plan_key,
        )
        import hashlib
        uid,pid,cid,vid=user_ids()
        original = AnalysisIdentity(uid,pid,cid,vid,"etag:source-unchanged",0.,10.)
        self.assertIn("frame-exact-v8", MODEL_VERSION)
        new_key = private_plan_key(original)
        # A new analyzer revision must never return older cached crops,
        # even when user, video generation, and clip times did not change.
        previous = AnalysisIdentity(uid,pid,cid,vid,"etag:source-unchanged",0.,10.)
        self.assertEqual(private_plan_key(previous),new_key)
        import app.services.smart_layout_cache as cache
        from unittest.mock import patch as mock_patch
        for prior in ("opencv-scene-20261019-live-wide-v3",
                      "opencv-scene-20261022-live-face-v4",
                      "opencv-scene-20261022-active-top-v5",
                      "opencv-scene-20261023-pairguard-v6",
                      "opencv-scene-20261030-cutguard-v7"):
            with mock_patch.object(cache, "MODEL_VERSION", prior):
                previous_key = private_plan_key(original)
            self.assertNotEqual(new_key, previous_key)

    async def test_cached_analysis_status_and_post_report_reuse_without_new_charge(self):
        uid, pid, cid, vid = user_ids()
        identity = AnalysisIdentity(uid, pid, cid, vid, "etag:billing", 0.0, 10.0)
        cached = {"status": "ready", "plans": {}}
        with patch.object(api, "_require_paid_feature", new_callable=AsyncMock), \
             patch.object(api, "_owned", new_callable=AsyncMock, return_value={}), \
             patch.object(api, "_identity", return_value=identity), \
             patch.object(api, "_cached", new_callable=AsyncMock, return_value=cached):
            status = await api.analysis_status(cid, {"id": uid})
            requested = await api.request_analysis(cid, BackgroundTasks(), {"id": uid})
        self.assertEqual(status["billing_action"], "cached_reuse")
        self.assertEqual(requested["billing_action"], "cached_reuse")
        self.assertEqual(status["plans"], requested["plans"])

    async def test_existing_analysis_job_is_not_reported_as_a_new_charge(self):
        uid, pid, cid, vid = user_ids()
        identity = AnalysisIdentity(uid, pid, cid, vid, "etag:billing", 0.0, 10.0)
        active = {"status": "processing", "job_id": str(uuid.uuid4())}
        with patch.object(api, "_require_paid_feature", new_callable=AsyncMock), \
             patch.object(api, "_owned", new_callable=AsyncMock, return_value={}), \
             patch.object(api, "_identity", return_value=identity), \
             patch.object(api, "_cached", new_callable=AsyncMock, return_value=None), \
             patch.object(api, "_active_job", new_callable=AsyncMock, return_value=active):
            status = await api.analysis_status(cid, {"id": uid})
        self.assertEqual(status["billing_action"], "existing_job")
        self.assertEqual(status["job_id"], active["job_id"])

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
        with patch.object(api,"_require_paid_feature",new_callable=AsyncMock,return_value={"enabled":True}), \
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
        with patch.object(api,"_require_paid_feature",new_callable=AsyncMock,return_value={"enabled":True}), \
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
        with patch.object(api,"_require_paid_feature",new_callable=AsyncMock,return_value={"enabled":True}), \
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


class SmartLayoutFreeTrialRolloutTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_free_accounts_are_ready_without_any_canary_or_paid_flag(self):
        first,second=user_ids()[:2]
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"false",
                                    "KARO_REAL_PREVIEW_CANARY_USERS":"",
                                    "KARO_REAL_PREVIEW_FREE_TRIAL_ENABLED":"true"}), \
             patch.object(api,"entitlement_status",new_callable=AsyncMock,
                          return_value={"enabled":True,"plan":"free","remaining":1,"allowance":1}):
            for uid in (first,second):
                status=await api.preview_capabilities({"id":uid})
                self.assertTrue(status["available"])
                self.assertEqual((status["plan"],status["remaining"] ),("free",1))
                self.assertEqual((await api._require_paid_feature({"id":uid}))["plan"],"free")

    async def test_free_trial_remains_accessible_to_view_saved_results_after_use(self):
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"false",
                                    "KARO_REAL_PREVIEW_FREE_TRIAL_ENABLED":"true"}), \
             patch.object(api,"entitlement_status",new_callable=AsyncMock,
                          return_value={"enabled":True,"plan":"free","remaining":0,"allowance":1}):
            status=await api.preview_capabilities({"id":str(uuid.uuid4())})
            self.assertTrue(status["available"])
            self.assertEqual(status["remaining"],0)

    async def test_explicit_free_trial_kill_switch_blocks_all_free_accounts(self):
        owner=str(uuid.uuid4())
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"true",
                                    "KARO_REAL_PREVIEW_CANARY_USERS":"*",
                                    "KARO_REAL_PREVIEW_FREE_TRIAL_ENABLED":"false"}), \
             patch.object(api,"entitlement_status",new_callable=AsyncMock,
                          return_value={"enabled":True,"plan":"free","remaining":1}):
            self.assertFalse((await api.preview_capabilities({"id":owner}))["available"])
            with self.assertRaises(HTTPException) as exc:
                await api._require_paid_feature({"id":owner})
            self.assertEqual(exc.exception.status_code,404)

    async def test_paid_account_cannot_bypass_canary_via_free_rollout(self):
        owner=str(uuid.uuid4())
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"false",
                                    "KARO_REAL_PREVIEW_CANARY_USERS":"",
                                    "KARO_REAL_PREVIEW_FREE_TRIAL_ENABLED":"true"}), \
             patch.object(api,"entitlement_status",new_callable=AsyncMock,
                          return_value={"enabled":True,"plan":"creator","remaining":12}):
            self.assertFalse((await api.preview_capabilities({"id":owner}))["available"])
            with self.assertRaises(HTTPException):
                await api._require_paid_feature({"id":owner})


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
            with patch.object(api, "entitlement_status", new_callable=AsyncMock,
                              return_value={"enabled":True, "plan":"creator", "remaining":12}):
                self.assertTrue((await api.preview_capabilities({"id":owner}))["available"])
            self.assertFalse((await api.preview_capabilities({"id":stranger}))["available"])
        with patch.dict(os.environ, {"KARO_REAL_PREVIEW_ENABLED":"false",
                                     "KARO_REAL_PREVIEW_CANARY_USERS":"*"}):
            self.assertFalse(api.enabled_for_user(owner))


class SmartLayoutExportCacheAliasTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_video_dimensions_match_preview_aliases(self):
        """Regression: displayed ANALYZED PREVIEW must not become export 409.

        Project/clip authorization and cache-key checks remain unchanged:
        only SQL column aliases differ between the two trusted code paths.
        """
        from app.services.smart_layout_contract import from_media_plan
        from app.services.smart_layout_cache import AnalysisIdentity, private_plan_key
        from app.services.smart_layout_cache import MODEL_VERSION
        identity = AnalysisIdentity(
            *user_ids(), generation="etag:verified-fixture",
            start=1.0, end=4.0,
        )
        variants = {}
        for mode in ("auto", "dual_stack", "speaker_focus"):
            evidence = SimpleNamespace(
                mode=mode, width=1280, height=720,
                segments=[SimpleNamespace(
                    start=0.0, end=3.0, mode="wide",
                    centers=(), switches=()
                )],
            )
            variants[mode] = from_media_plan(
                evidence, source_start=1.0, duration=3.0
            )
        cache = {
            "version": 2, "model_version": MODEL_VERSION,
            "cache_key": private_plan_key(identity), "plans": variants,
        }
        with patch("app.services.smart_layout_repository.read_plan",
                   new_callable=AsyncMock, return_value=cache):
            preview = await api._cached(
                {"source_width": 1280, "source_height": 720}, identity
            )
            export = await api._cached(
                {"width": 1280, "height": 720}, identity
            )
            self.assertEqual(preview, export)
            self.assertEqual(export["status"], "ready")
            self.assertIn("dual_stack", export["plans"])
            self.assertIn("speaker_focus", export["plans"])
            self.assertIsNone(await api._cached(
                {"width": 640, "height": 360}, identity
            ))
            self.assertIsNone(await api._cached(
                {"width": 1280}, identity
            ))

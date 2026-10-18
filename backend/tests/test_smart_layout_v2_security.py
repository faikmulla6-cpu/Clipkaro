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

    async def test_malformed_cache_never_returned_or_marked_ready(self):
        uid,pid,cid,vid=user_ids()
        identity=AnalysisIdentity(uid,pid,cid,vid,"etag:xyz",0.,2.)
        key=private_plan_key(identity)
        payload=json.dumps({"version":2,"cache_key":key,"plans":{"auto":{"scenes":["../../etc"]}}}).encode()
        class Storage:
            async def stat(self,k):return SimpleNamespace(size=len(payload),generation="etag:xyz")
            async def download(self,k,destination):
                destination.write_bytes(payload)
        with patch.object(api,"get_storage_provider",return_value=Storage()):
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
        fake=FakeS3()
        fake.client.get_object.side_effect=lambda **kw:{
            "Body":io.BytesIO(source[int(kw["Range"].split("=")[1].split("-")[0]):int(kw["Range"].split("-")[-1])+1])
        }
        scope={"type":"http","method":"GET","path":"/v1/test",
               "headers":[(b"range",b"bytes=2-9")]}
        req=Request(scope)
        owned={"original_filename":"a.mp4","file_path":key,"object_generation":"etag:abc"}
        with patch.object(api,"enabled",return_value=True), \
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

    async def test_cross_generation_media_fails_closed(self):
        uid,pid,cid,vid=user_ids()
        key=f"users/{uid}/projects/{pid}/videos/{vid}/source.mp4"
        class FakeS3:
            bucket="hidden"
            async def stat(self,k):return SimpleNamespace(size=777,generation="etag:new")
        row={"original_filename":"a.mp4","file_path":key,"object_generation":"etag:old"}
        req=Request({"type":"http","method":"GET","path":"/v1/test","headers":[]})
        with patch.object(api,"enabled",return_value=True), \
             patch.object(api,"_owned",new_callable=AsyncMock,return_value=row), \
             patch.object(api,"get_storage_provider",return_value=FakeS3()), \
             patch.object(api,"S3StorageProvider",FakeS3), \
             patch.object(api,"get_settings",return_value=SimpleNamespace(normalized_storage_backend="gcs")):
            with self.assertRaises(HTTPException) as exc:
                await api.original_canvas_video(cid,req,{"id":uid})
        self.assertEqual(exc.exception.status_code,409)


if __name__=="__main__":
    unittest.main()


class SmartLayoutPurgeScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_explicit_owner_project_analysis_versions_can_be_purged(self):
        from app.services import smart_layout_cleanup as cleanup
        from app.services.smart_layout_cache import AnalysisIdentity,private_plan_key
        uid,pid,cid,vid=user_ids()
        key=private_plan_key(AnalysisIdentity(uid,pid,cid,vid,"etag:v1",0,5))
        class FakeS3:
            bucket="private"
            def __init__(self):
                self.client=MagicMock()
                self.client.list_object_versions.return_value={
                    "Versions":[{"Key":key,"VersionId":"1234"}],
                    "DeleteMarkers":[{"Key":key,"VersionId":"dead"}],
                    "IsTruncated":False}
        fake=FakeS3()
        with patch.object(cleanup,"S3StorageProvider",FakeS3):
            count=await cleanup.purge_smart_layout_plans(fake,uid,pid)
        self.assertEqual(count,2)
        self.assertEqual(fake.client.delete_object.call_count,2)
        for call in fake.client.delete_object.call_args_list:
            self.assertEqual(call.kwargs["Key"],key)

    async def test_unexpected_object_refuses_entire_purge_page(self):
        from app.services import smart_layout_cleanup as cleanup
        from app.services.smart_layout_cache import AnalysisIdentity,private_plan_key
        uid,pid,cid,vid=user_ids()
        key=private_plan_key(AnalysisIdentity(uid,pid,cid,vid,"etag:v1",0,5))
        other_uid=str(uuid.uuid4())
        forbidden=key.replace(uid,other_uid)
        class FakeS3:
            bucket="private"
            def __init__(self):
                self.client=MagicMock()
                self.client.list_object_versions.return_value={
                    "Versions":[{"Key":key,"VersionId":"good"},{"Key":forbidden,"VersionId":"bad"}],
                    "IsTruncated":False}
        fake=FakeS3()
        with patch.object(cleanup,"S3StorageProvider",FakeS3):
            with self.assertRaises(ValueError):
                await cleanup.purge_smart_layout_plans(fake,uid,pid)
        fake.client.delete_object.assert_not_called()

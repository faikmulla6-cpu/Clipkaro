import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.post_karo import POST_KARO_PLANS, _eligible
from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.main import app
from app.services.billing import PLAN_CATALOG
from app.services.legal import LEGAL_VERSION
from app.services.post_karo import (
    PostKaroProviderError,
    ZernioClient,
    _post_response,
    _provider_profile_id,
    build_post_payload,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
    sync_supported_accounts,
    validate_api_key_shape,
)


@pytest.fixture()
def client(tmp_path):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "post_karo_encryption_key": settings.post_karo_encryption_key,
        "seed_demo_user": settings.seed_demo_user,
    }
    settings.database_path = tmp_path / "post-karo.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "post-karo-unit-test-secret"
    settings.post_karo_encryption_key = "post-karo-dedicated-unit-test-secret-with-32-chars"
    settings.seed_demo_user = True
    settings.app_env = "test"
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def login_demo(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@clipkaro.ai", "password": "ClipKaro123!"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post(
        "/api/v1/legal/accept",
        json={"accepted": True, "version": LEGAL_VERSION},
    )
    assert accepted.status_code == 200


def seed_ready_export() -> None:
    now = datetime.now(timezone.utc)
    created = now.isoformat()
    expires = (now + timedelta(hours=24)).isoformat()
    asyncio.run(execute(
        """INSERT INTO projects(
             id,user_id,title,status,progress,stage,language,category,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("pk-project", "demo-user", "Post Karo source", "ready", 100, "ready", "en", "creator", created, created),
    ))
    asyncio.run(execute(
        """INSERT INTO videos(
             id,project_id,original_filename,duration,width,height,file_size,file_path,status,created_at,expires_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        ("pk-video", "pk-project", "source.mp4", 60, 1080, 1920, 100, "test-source.mp4", "ready", created, expires),
    ))
    asyncio.run(execute(
        """INSERT INTO clips(
             id,video_id,start_time,end_time,hook,title,reason,transcript_text,score,
             score_breakdown_json,platform,status,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("pk-clip", "pk-video", 0, 30, "Hook", "Original title", "Reason", "Transcript", 88,
         "{}", "youtube", "suggested", created, created),
    ))
    asyncio.run(execute(
        """INSERT INTO exports(
             id,clip_id,user_id,output_path,resolution,aspect_ratio,caption_style,watermark,
             status,progress,error,created_at,expires_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("pk-export", "pk-clip", "demo-user", "test-export.mp4", "1080p", "9:16",
         "kinetic", 0, "ready", 100, None, created, expires),
    ))


def synthetic_zernio_key() -> str:
    return "".join(("s", "k", "_")) + ("a" * 64)


def seed_connection() -> None:
    now = datetime.now(timezone.utc).isoformat()
    key = synthetic_zernio_key()
    asyncio.run(execute(
        """INSERT INTO post_karo_connections(
             user_id,api_key_ciphertext,api_key_masked,api_key_fingerprint,profile_id,
             validated_at,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?)""",
        ("demo-user", encrypt_api_key(key), mask_api_key(key), "test-fingerprint", "profile-1", now, now, now),
    ))
    for platform, account_id, name in (
        ("instagram", "ig-1", "@clipkaro"),
        ("youtube", "yt-1", "ClipKaro Channel"),
    ):
        asyncio.run(execute(
            """INSERT INTO post_karo_accounts(
                 id,user_id,platform,provider_account_id,username,display_name,can_post,
                 connection_status,health_json,last_synced_at,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,1,'connected','{}',?,?,?)""",
            (str(uuid.uuid4()), "demo-user", platform, account_id, name, name, now, now, now),
        ))


def test_api_key_is_encrypted_and_masked():
    key = synthetic_zernio_key()
    assert validate_api_key_shape(key) == key
    ciphertext = encrypt_api_key(key)
    assert key not in ciphertext
    assert decrypt_api_key(ciphertext) == key
    masked = mask_api_key(key)
    assert key not in masked
    assert masked.startswith("sk_aaaa") and masked.endswith("aaaa")


def test_payload_preserves_creator_edits_and_partial_results():
    snapshot = {
        "instagram_enabled": True,
        "instagram_caption": "Edited Instagram caption",
        "instagram_hashtags": ["#edited", "#clipkaro"],
        "youtube_enabled": True,
        "youtube_title": "Edited YouTube title",
        "youtube_description": "Edited YouTube description",
        "youtube_tags": ["edited", "shorts"],
        "youtube_visibility": "unlisted",
        "mode": "now",
    }
    accounts = {
        "instagram": {"provider_account_id": "ig-1", "can_post": 1},
        "youtube": {"provider_account_id": "yt-1", "can_post": 1},
    }
    payload = build_post_payload(snapshot, accounts, "https://media.example/short.mp4")
    instagram, youtube = payload["platforms"]
    assert instagram["customContent"] == "Edited Instagram caption\n\n#edited #clipkaro"
    assert youtube["customContent"] == "Edited YouTube description"
    assert youtube["platformSpecificData"]["title"] == "Edited YouTube title"
    assert youtube["platformSpecificData"]["visibility"] == "unlisted"
    assert payload["tags"] == ["edited", "shorts"]
    status, _, results = _post_response({
        "post": {
            "status": "partial",
            "platforms": [
                {"platform": "instagram", "status": "published", "platformPostUrl": "https://instagram.example/reel"},
                {"platform": "youtube", "status": "failed", "error": "rejected"},
            ],
        }
    })
    assert status == "partial"
    assert results[0]["platformPostUrl"]


def test_publish_rejects_stale_revision_and_snapshots_exact_saved_revision(client: TestClient):
    login_demo(client)
    seed_ready_export()
    seed_connection()
    created = client.post("/api/v1/post-karo/drafts/from-export/pk-export")
    assert created.status_code == 201
    draft = created.json()
    assert draft["revision"] == 1

    saved = client.patch(
        f"/api/v1/post-karo/drafts/{draft['id']}",
        json={
            "expected_revision": 1,
            "instagram_caption": "Latest creator caption",
            "youtube_title": "Latest creator title",
            "youtube_description": "Latest creator description",
            "youtube_visibility": "private",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2

    stale = client.post(
        f"/api/v1/post-karo/drafts/{draft['id']}/publish",
        json={"expected_revision": 1, "request_id": str(uuid.uuid4()), "mode": "now"},
    )
    assert stale.status_code == 409
    assert asyncio.run(fetch_all("SELECT * FROM post_karo_publications")) == []

    request_id = str(uuid.uuid4())
    with patch("app.api.post_karo.dispatch_job", new=AsyncMock()):
        publish = client.post(
            f"/api/v1/post-karo/drafts/{draft['id']}/publish",
            json={"expected_revision": 2, "request_id": request_id, "mode": "now"},
        )
    assert publish.status_code == 202
    body = publish.json()
    assert body["draft_revision"] == 2
    assert body["snapshot"]["instagram_caption"] == "Latest creator caption"
    assert body["snapshot"]["youtube_title"] == "Latest creator title"
    assert body["snapshot"]["youtube_description"] == "Latest creator description"
    assert body["snapshot"]["youtube_visibility"] == "private"
    publication = asyncio.run(fetch_one(
        "SELECT snapshot_json,draft_revision,request_id FROM post_karo_publications WHERE id=?",
        (body["id"],),
    ))
    assert publication and publication["draft_revision"] == 2
    assert publication["request_id"] == request_id
    stored = json.loads(publication["snapshot_json"])
    assert stored["instagram_caption"] == "Latest creator caption"
    assert stored["youtube_title"] == "Latest creator title"


def test_post_karo_is_strictly_user_scoped(client: TestClient):
    login_demo(client)
    seed_ready_export()
    seed_connection()
    created = client.post("/api/v1/post-karo/drafts/from-export/pk-export")
    assert created.status_code == 201
    draft_id = created.json()["id"]

    status = client.get("/api/v1/post-karo/status")
    assert status.status_code == 200
    body = status.json()
    assert "api_key_ciphertext" not in body
    assert "api_key_fingerprint" not in body
    assert body["api_key_masked"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    signup = client.post(
        "/api/v1/auth/signup",
        json={"name": "Other Creator", "email": "other-post-karo@example.com", "password": "Secure123!"},
    )
    assert signup.status_code == 201
    other_id = signup.json()["user"]["id"]
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    accepted = client.post(
        "/api/v1/legal/accept",
        json={"accepted": True, "version": LEGAL_VERSION},
    )
    assert accepted.status_code == 200
    asyncio.run(execute("UPDATE users SET plan='growth' WHERE id=?", (other_id,)))
    assert client.get("/api/v1/post-karo/drafts/" + draft_id).status_code == 404
    assert client.patch(
        "/api/v1/post-karo/drafts/" + draft_id,
        json={"expected_revision": 1, "instagram_caption": "Attempted cross-user edit"},
    ).status_code == 404
    assert client.post(
        "/api/v1/post-karo/drafts/from-export/pk-export",
        json={},
    ).status_code == 404
    assert client.get("/api/v1/post-karo/publications").json() == []


def test_post_karo_is_available_on_every_clipkaro_plan():
    assert POST_KARO_PLANS == set(PLAN_CATALOG)
    for plan in PLAN_CATALOG:
        assert _eligible({"plan": plan, "role": "creator"}) is True
    assert _eligible({"plan": "unknown", "role": "creator"}) is False
    assert _eligible({"plan": "unknown", "role": "admin"}) is True


def test_post_karo_free_access_does_not_change_plan_role_or_billing(client: TestClient):
    login_demo(client)
    asyncio.run(execute(
        """UPDATE users
           SET plan='free',role='creator',billing_reference=NULL,post_karo_access_override=0
           WHERE id='demo-user'"""
    ))

    status = client.get("/api/v1/post-karo/status")
    assert status.status_code == 200
    assert status.json()["plan_eligible"] is True

    user = asyncio.run(fetch_one(
        "SELECT plan,role,billing_reference,post_karo_access_override FROM users WHERE id='demo-user'"
    ))
    assert user == {
        "plan": "free",
        "role": "creator",
        "billing_reference": None,
        "post_karo_access_override": 0,
    }


def test_zernio_list_accounts_does_not_send_unpaired_limit():
    client = ZernioClient(synthetic_zernio_key())
    with patch.object(
        client,
        "_request",
        new=AsyncMock(return_value=(200, {"accounts": []})),
    ) as request:
        result = asyncio.run(client.list_accounts("66a1f0c2a4b9d3e8f1a2b3c4"))
    assert result == []
    request.assert_awaited_once_with(
        "GET",
        "/v1/accounts",
        params={"profileId": "66a1f0c2a4b9d3e8f1a2b3c4"},
    )


def test_connection_sync_provider_error_is_controlled_not_500(client: TestClient):
    login_demo(client)
    asyncio.run(execute(
        "UPDATE users SET plan='free' WHERE id='demo-user'"
    ))
    with (
        patch(
            "app.api.post_karo.ZernioClient.validate",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.api.post_karo.ZernioClient.ensure_clipkaro_profile",
            new=AsyncMock(return_value="66a1f0c2a4b9d3e8f1a2b3c4"),
        ),
        patch(
            "app.api.post_karo.sync_supported_accounts",
            new=AsyncMock(
                side_effect=PostKaroProviderError(
                    "The publishing service could not accept this request.",
                    status_code=400,
                )
            ),
        ),
    ):
        response = client.post(
            "/api/v1/post-karo/connection/test",
            json={"api_key": synthetic_zernio_key()},
        )
    assert response.status_code == 400
    assert response.status_code != 500
    assert "publishing service" in response.json()["detail"].lower()


def test_provider_profile_id_accepts_string_and_populated_object():
    profile_id = "66a1f0c2a4b9d3e8f1a2b3c4"
    assert _provider_profile_id({"profileId": profile_id}) == profile_id
    assert _provider_profile_id({"profileId": {"_id": profile_id, "name": "ClipKaro"}}) == profile_id
    assert _provider_profile_id({"profile": {"_id": profile_id}}) == profile_id


def test_sync_accepts_populated_profile_id_object(client: TestClient):
    login_demo(client)
    profile_id = "66a1f0c2a4b9d3e8f1a2b3c4"
    with (
        patch(
            "app.services.post_karo.ZernioClient.list_accounts",
            new=AsyncMock(return_value=[{
                "_id": "ig-account-1",
                "platform": "instagram",
                "profileId": {"_id": profile_id, "name": "ClipKaro"},
                "username": "creator",
                "displayName": "Creator",
                "isActive": True,
            }]),
        ),
        patch(
            "app.services.post_karo.ZernioClient.account_health",
            new=AsyncMock(return_value=[{
                "accountId": "ig-account-1",
                "canPost": True,
            }]),
        ),
    ):
        rows = asyncio.run(
            sync_supported_accounts("demo-user", synthetic_zernio_key(), profile_id)
        )

    assert len(rows) == 1
    assert rows[0]["platform"] == "instagram"
    assert rows[0]["connection_status"] == "connected"
    assert rows[0]["can_post"] == 1


def test_zernio_presigned_upload_sends_exact_content_length(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    source = tmp_path / "short.mp4"
    source.write_bytes(b"clipkaro-video-bytes")
    observed: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def put(self, url, *, headers, content):
            observed["url"] = url
            observed["headers"] = headers
            uploaded = bytearray()
            async for block in content:
                uploaded.extend(block)
            observed["content"] = bytes(uploaded)
            return FakeResponse()

    client = ZernioClient(synthetic_zernio_key())
    monkeypatch.setattr(
        client,
        "_request",
        AsyncMock(return_value=(200, {
            "uploadUrl": "https://upload.example/object",
            "publicUrl": "https://media.example/short.mp4",
        })),
    )
    monkeypatch.setattr("app.services.post_karo.httpx.AsyncClient", FakeAsyncClient)

    public_url = asyncio.run(client.upload_media(source))

    assert public_url == "https://media.example/short.mp4"
    assert observed["content"] == source.read_bytes()
    assert observed["headers"] == {
        "Content-Type": "video/mp4",
        "Content-Length": str(source.stat().st_size),
    }

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_one
from app.main import _auth_requests, _requests, app
from app.services import cartoon_job
from app.services.cartoon_job import CartoonJobError, _apply_cinematic_jannat_storyboard, _normalize_storyboard, _tts_audio, _voice_for
from app.services.cartoon_renderer import build_cartoon_project
from app.services.cartoon_security import decrypt_provider_key, encrypt_provider_key


class _FakeResponse:
    def __init__(self, content: bytes, content_type: str, status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": content_type}


class _FakeClient:
    response = _FakeResponse(b"\x00" * 256, "audio/mpeg")
    request = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, *, headers, json):
        type(self).request = {"url": url, "headers": headers, "json": json}
        return type(self).response


def test_storyboard_normalization_keeps_character_identity_and_escapes_untrusted_text():
    storyboard = _normalize_storyboard(
        {
            "title": "A safe story",
            "characters": [
                {
                    "id": "hero",
                    "name": "<script>alert(1)</script>",
                    "role": "explorer",
                    "voice_type": "male",
                    "appearance": {
                        "skin_color": "red; background:url(javascript:alert(1))",
                        "shirt_color": "#12AB34",
                        "hair_style": "long",
                    },
                }
            ],
            "scenes": [
                {
                    "scene_title": "First <script>",
                    "environment": "javascript",
                    "action": "<script>run()</script>",
                    "dialogue": "Hello <script>run()</script>",
                    "speaker_id": "hero",
                    "character_ids": ["hero"],
                },
                {
                    "scene_title": "Second scene",
                    "environment": "forest",
                    "action": "The hero waves",
                    "dialogue": "Let's go!",
                    "speaker_id": "hero",
                    "character_ids": ["hero"],
                },
            ],
        },
        scene_count=2,
        prompt="A fox finds a map",
    )
    assert [scene["speaker_id"] for scene in storyboard["scenes"]] == ["hero", "hero"]
    assert [scene["character_ids"] for scene in storyboard["scenes"]] == [["hero"], ["hero"]]
    assert storyboard["characters"][0]["appearance"]["skin_color"] == "#E9B58F"
    assert storyboard["characters"][0]["appearance"]["shirt_color"] == "#12AB34"
    assert storyboard["scenes"][0]["environment"] == "forest"

    files = build_cartoon_project(
        {"duration_seconds": 15, "aspect_ratio": "9:16", "style": "2d-cartoon", "language": "hi"},
        storyboard,
        [],
    )
    assert "index.html" in files
    assert "compositions/scene-1.html" in files
    html = "".join(files.values())
    assert "<script>run()" not in html
    assert "&lt;script&gt;run()&lt;/script&gt;" not in html  # Scene directions are not rendered as on-screen text.
    assert "background:url(javascript" not in html
    assert 'data-composition-src="compositions/scene-1.html"' in files["index.html"]
    assert "<template>" in files["compositions/scene-1.html"]


def test_voice_selection_uses_model_specific_gendered_presets():
    assert _voice_for({"voice_type": "male"}, ["af_alloy", "am_adam"]) == "am_adam"
    assert _voice_for({"voice_type": "female"}, ["en_paul_neutral", "gb_jane_curious"]) == "gb_jane_curious"
    assert _voice_for({"voice_type": "child"}, ["am_puck", "hf_alpha"]) == "hf_alpha"
    assert _voice_for({"voice_type": "male"}, ["am_adam", "hm_omega"], "hi") == "hm_omega"
    assert _voice_for({"voice_type": "female"}, ["george", "sarah"], "hinglish",
                      saved_voice="george", strict=True) == "sarah"
    assert _voice_for({"voice_type": "female"}, ["Puck", "Kore", "Zephyr"], "hinglish",
                      saved_voice="Zephyr", strict=True) == "Zephyr"
    assert _voice_for({"voice_type": "female"}, ["Puck", "kore"], "hinglish",
                      strict=True) == "kore"
    with pytest.raises(CartoonJobError, match="known female voice"):
        _voice_for({"voice_type": "female"}, ["george"], "hinglish", strict=True)
    assert _voice_for({"voice_type": "female"}, ["af_heart", "hf_alpha"], "hi") == "hf_alpha"


def test_species_inference_and_animal_rigs_keep_their_identity():
    storyboard = _normalize_storyboard(
        {
            "characters": [
                {"id": "milo", "name": "Milo", "role": "curious fox", "voice_type": "male"},
                {"id": "ollie", "name": "Ollie", "role": "wise owl", "voice_type": "male"},
            ],
            "scenes": [
                {"scene_title": "The map", "action": "Milo finds a map", "dialogue": "Look!", "speaker_id": "milo", "character_ids": ["milo", "ollie"]},
                {"scene_title": "A clue", "action": "Ollie points at the stars", "dialogue": "Follow me!", "speaker_id": "ollie", "character_ids": ["milo", "ollie"]},
            ],
        },
        scene_count=2,
        prompt="A fox and an owl go on an adventure",
    )
    assert [item["species"] for item in storyboard["characters"]] == ["fox", "owl"]
    files = build_cartoon_project(
        {"duration_seconds": 15, "aspect_ratio": "9:16", "style": "2d-cartoon", "language": "hi"},
        storyboard,
        [],
    )
    first_scene = files["compositions/scene-1.html"]
    second_scene = files["compositions/scene-2.html"]
    assert 'data-species="fox"' in first_scene
    assert 'id="char-1-milo-tail"' in first_scene
    assert 'data-species="owl"' in second_scene
    assert 'id="char-2-ollie-tail"' in second_scene


def test_provider_key_encryption_round_trips_and_does_not_store_plaintext(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "secret_key", "cartoon-test-secret-with-more-than-32-characters")
    key = "sk-or-test-key-with-sufficient-length"
    ciphertext = encrypt_provider_key(key)
    assert ciphertext.startswith("v1:")
    assert key not in ciphertext
    assert decrypt_provider_key(ciphertext) == key


@pytest.mark.asyncio
async def test_tts_mp3_uses_openrouter_speech_endpoint_and_saves_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(cartoon_job.httpx, "AsyncClient", _FakeClient)
    _FakeClient.response = _FakeResponse(b"\x01" * 256, "audio/mpeg")
    output = tmp_path / "scene-1.mp3"

    await _tts_audio(
        "sk-or-test",
        "mistralai/voxtral-mini-tts-2603",
        "en_paul_neutral",
        "Hello from ClipKaro.",
        output,
    )

    assert output.read_bytes() == b"\x01" * 256
    assert _FakeClient.request["url"].endswith("/audio/speech")
    assert _FakeClient.request["json"] == {
        "model": "mistralai/voxtral-mini-tts-2603",
        "input": "Hello from ClipKaro.",
        "voice": "en_paul_neutral",
        "response_format": "mp3",
    }


@pytest.mark.asyncio
async def test_tts_pcm_uses_provider_sample_rate_and_channel_count(tmp_path, monkeypatch):
    monkeypatch.setattr(cartoon_job.httpx, "AsyncClient", _FakeClient)
    _FakeClient.response = _FakeResponse(b"\x01" * 512, "audio/pcm;rate=22050;channels=2")
    monkeypatch.setattr(cartoon_job.shutil, "which", lambda name: "ffmpeg" if name == "ffmpeg" else None)
    captured = {}

    async def fake_to_thread(function, *args, **kwargs):
        command = args[0]
        captured["command"] = command
        Path(command[-1]).write_bytes(b"\x02" * 256)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cartoon_job.asyncio, "to_thread", fake_to_thread)
    output = tmp_path / "scene-1.mp3"

    await _tts_audio(
        "sk-or-test",
        "google/gemini-3.1-flash-tts-preview",
        "Puck",
        "Hello from ClipKaro.",
        output,
    )

    command = captured["command"]
    assert command[command.index("-ar") + 1] == "22050"
    assert command[command.index("-ac") + 1] == "2"
    assert _FakeClient.request["json"]["response_format"] == "pcm"
    assert output.stat().st_size == 256
    assert not output.with_suffix(".pcm").exists()

    kokoro_output = tmp_path / "kokoro.mp3"
    await _tts_audio(
        "sk-or-test",
        "hexgrad/kokoro-82m",
        "hf_alpha",
        "Namaste from ClipKaro.",
        kokoro_output,
    )
    assert _FakeClient.request["json"]["response_format"] == "pcm"
    assert kokoro_output.stat().st_size == 256


@pytest.mark.asyncio
async def test_tts_rejects_json_error_body_even_when_status_is_success(tmp_path, monkeypatch):
    monkeypatch.setattr(cartoon_job.httpx, "AsyncClient", _FakeClient)
    _FakeClient.response = _FakeResponse(b'{"error":"' + b"x" * 200 + b'"}', "application/json")

    with pytest.raises(CartoonJobError) as raised:
        await _tts_audio(
            "sk-or-test",
            "mistralai/voxtral-mini-tts-2603",
            "en_paul_neutral",
            "Hello.",
            tmp_path / "invalid.mp3",
        )

    assert raised.value.category == "CARTOON_TTS_INVALID_RESPONSE"


@pytest.fixture()
def cartoon_api_client(tmp_path):
    settings = get_settings()
    original = {
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
        "app_env": settings.app_env,
        "email_verification_required": settings.email_verification_required,
        "upload_scan_required": settings.upload_scan_required,
        "clamav_host": settings.clamav_host,
        "job_execution_mode": settings.job_execution_mode,
    }
    settings.database_path = tmp_path / "cartoon-api.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "cartoon-api-test-secret-with-more-than-32-characters"
    settings.seed_demo_user = False
    settings.app_env = "test"
    settings.email_verification_required = False
    settings.upload_scan_required = False
    settings.clamav_host = ""
    settings.job_execution_mode = "worker"
    _requests.clear()
    _auth_requests.clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
        _requests.clear()
        _auth_requests.clear()


def test_cartoon_api_denies_accounts_without_explicit_access(cartoon_api_client):
    client = cartoon_api_client
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Cartoon Creator",
            "email": "cartoon-no-access@example.com",
            "password": "Secure123",
        },
    )
    assert signup.status_code == 201, signup.text
    assert signup.json()["user"]["cartoon_studio_access_override"] is False
    response = client.get("/api/v1/cartoon-studio/providers")
    assert response.status_code == 403
    assert "beta access is not enabled" in response.json()["detail"].lower()


def test_cartoon_api_connects_byok_and_queues_private_project(cartoon_api_client):
    client = cartoon_api_client
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Cartoon Creator",
            "email": "cartoon-api@example.com",
            "password": "Secure123",
        },
    )
    assert signup.status_code == 201, signup.text
    asyncio.run(execute(
        "UPDATE users SET cartoon_studio_access_override=1 WHERE email=?",
        ("cartoon-api@example.com",),
    ))
    access = client.get("/api/v1/auth/me")
    assert access.status_code == 200, access.text
    assert access.json()["cartoon_studio_access_override"] is True
    csrf = {"X-CSRF-Token": client.cookies.get("csrf_token")}
    key = "sk-or-test-cartoon-api-key-with-sufficient-length"
    tts_model = "google/gemini-3.1-flash-tts-preview"
    models = [
        {
            "id": tts_model,
            "name": "Google Gemini 3.1 Flash TTS Preview",
            "supported_voices": ["Puck", "Kore"],
            "description": "Test speech model",
        },
        {
            "id": "fish-audio/s1",
            "name": "Fish Audio S1",
            "supported_voices": None,
            "description": "No published preset voice list",
        },
    ]

    with patch("app.api.cartoon_studio._models", new=AsyncMock(return_value=models)) as discover:
        connected = client.post(
            "/api/v1/cartoon-studio/providers/openrouter",
            headers=csrf,
            json={"api_key": key},
        )
        assert connected.status_code == 200, connected.text
        assert key not in connected.text
        assert connected.json()["connected"] is True

        provider_status = client.get("/api/v1/cartoon-studio/providers")
        assert provider_status.status_code == 200
        assert provider_status.json()["openrouter"]["connected"] is True

        available = client.get("/api/v1/cartoon-studio/tts-models")
        assert available.status_code == 200, available.text
        assert available.json()["default_model"] == "system/kokoro-82m"
        assert [model["id"] for model in available.json()["models"]] == [
            "system/kokoro-82m", "system/edge-tts-urdu", "system/edge-tts-regional",
        ]
        assert "hf_alpha" in available.json()["models"][0]["voices_by_language"]["hi"]

        selection = {
            "prompt": "A little fox finds a glowing map in the forest",
            "duration_seconds": "15",
            "aspect_ratio": "9:16",
            "style": "2d-cartoon",
            "language": "hi",
        }
        rejected = client.post(
            "/api/v1/cartoon-studio/projects",
            headers=csrf,
            data={**selection, "tts_model": tts_model},
        )
        assert rejected.status_code == 422
        created = client.post(
            "/api/v1/cartoon-studio/projects", headers=csrf,
            data={**selection, "voice_id": "hf_alpha"},
        )
        assert created.status_code == 200, created.text
        project = created.json()
        assert project["status"] == "queued"
        assert project["duration_seconds"] == 15
        assert project["storyboard"] == {}

    user = asyncio.run(fetch_one(
        "SELECT * FROM users WHERE email=?",
        ("cartoon-api@example.com",),
    ))
    credential = asyncio.run(fetch_one(
        "SELECT * FROM cartoon_provider_credentials WHERE user_id=? AND provider='openrouter'",
        (user["id"],),
    ))
    job = asyncio.run(fetch_one("SELECT * FROM jobs WHERE id=?", (project["job_id"],)))
    job_payload = asyncio.run(fetch_one("SELECT * FROM job_payloads WHERE job_id=?", (project["job_id"],)))
    assert credential and credential["api_key_ciphertext"].startswith("v1:")
    assert key not in credential["api_key_ciphertext"]
    assert job and job["kind"] == "cartoon_generate" and job["status"] == "queued"
    assert job_payload and project["id"] in job_payload["payload_json"]
    assert key not in job_payload["payload_json"]
    saved_project = asyncio.run(fetch_one("SELECT * FROM cartoon_projects WHERE id=?", (project["id"],)))
    assert saved_project["tts_model"] == "system/kokoro-82m"
    assert json.loads(saved_project["assets_json"])["_preferred_voice"] == "hf_alpha"
    path = "/api/v1/cartoon-studio/projects/" + project["id"]
    assert "caption_timeline" not in client.get(path).json()
    cue = {"id": "line-one", "speaker": "Fox", "text": "I found it!", "start_seconds": 1.2, "end_seconds": 2.8}
    asyncio.run(execute("UPDATE cartoon_projects SET status='ready',output_key=?,assets_json=? WHERE id=?", (
        f"users/{user['id']}/cartoons/{project['id']}/final.mp4",
        json.dumps({"_caption_timeline": [cue], "_editable": {"key": "private.zip"}}), project["id"],
    )))
    assert client.get(path).json()["caption_timeline"] == [cue]
    assert "caption_timeline" not in client.get("/api/v1/cartoon-studio/projects").json()[0]
    assert client.get(path + "/download").status_code == 200
    assert client.get(path + "/editable").status_code == 404
    assert client.get(path + "/editable-file").status_code == 404
    discover.assert_awaited_once()


def test_saved_nvidia_key_is_reused_and_independently_disconnected(cartoon_api_client, monkeypatch):
    import httpx
    from story_v3_fixtures import fixtures

    client = cartoon_api_client
    prefix = "/api/v1/cartoon-studio"
    email = "saved-nvidia@example.com"
    assert client.post("/api/v1/auth/signup", json={
        "name": "NVIDIA tester", "email": email, "password": "Secure123",
    }).status_code == 201
    user = asyncio.run(fetch_one("SELECT id FROM users WHERE email=?", (email,)))
    user_id = user["id"]
    asyncio.run(execute("UPDATE users SET cartoon_studio_access_override=1 WHERE id=?", (user_id,)))
    csrf = {"X-CSRF-Token": client.cookies.get("csrf_token")}
    key = "nvapi-test-nvidia-encrypted-connection"
    endpoint = prefix + "/providers/nvidia"
    assert client.post(endpoint, headers=csrf, json={"api_key": key}).status_code == 403
    monkeypatch.setattr(get_settings(), "cartoon_storyboard_test_user_ids", user_id)
    assert client.post(endpoint, json={"api_key": key}).status_code == 403

    invalid = client.post(endpoint, headers=csrf, json={"api_key": [key]})
    assert invalid.status_code == 422 and key not in invalid.text
    connected = client.post(endpoint, headers=csrf, json={"api_key": key})
    assert connected.status_code == 200 and key not in connected.text
    assert connected.json()["connected"] is True and connected.json()["validated_at"] is None
    nav = client.get(prefix + "/providers")
    assert nav.json()["nvidia"] == connected.json()
    assert key not in nav.text
    assert nav.headers["cache-control"] == "no-store"
    credential = asyncio.run(fetch_one(
        "SELECT api_key_ciphertext FROM cartoon_provider_credentials WHERE user_id=? AND provider='nvidia'", (user_id,),
    ))
    assert credential["api_key_ciphertext"].startswith("v1:") and key not in credential["api_key_ciphertext"]

    idea = {"prompt": "A fox finds the lost ball.", "duration_seconds": "15", "language": "ur"}
    upstream = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(fixtures()["garden"])}}]})
    with patch("app.api.cartoon_studio._models", new=AsyncMock(return_value=[])), patch(
        "app.api.cartoon_studio.request_storyboard", new=AsyncMock(return_value=upstream),
    ) as plan:
        assert client.get(prefix + "/tts-models").status_code == 200
        tested = client.post(prefix + "/storyboard-test", headers=csrf, data={**idea, "provider": "nvidia"})
        assert tested.status_code == 200 and key not in tested.text
        created = client.post(prefix + "/projects", headers=csrf, data={
            **idea, "story_planner": "nvidia",
        })
        assert created.status_code == 200 and key not in created.text
        project = created.json()
        assert project["status"] == "queued" and project["storyboard"] == {}
        plan.assert_awaited_once()
        assert plan.await_args.args[0] == key and plan.await_args.kwargs["provider"] == "nvidia"
    job_payload = asyncio.run(fetch_one("SELECT payload_json FROM job_payloads WHERE job_id=?", (project["job_id"],)))
    assert key not in job_payload["payload_json"]
    assert client.delete(endpoint, headers=csrf).status_code == 204
    remaining = client.get(prefix + "/providers").json()
    assert not remaining["nvidia"]["connected"] and not remaining["openrouter"]["connected"]
    missing = client.post(prefix + "/storyboard-test", headers=csrf, data={**idea, "provider": "nvidia"})
    assert missing.status_code == 409


@pytest.mark.asyncio
async def test_serverless_media_job_dispatches_cartoon_to_dedicated_pipeline(tmp_path, monkeypatch):
    from app import media_job

    storage = object()
    monkeypatch.setattr(media_job, "get_storage_provider", lambda: storage)
    job = {
        "id": "cartoon-media-job",
        "kind": "cartoon_generate",
        "user_id": "cartoon-user",
        "payload": {"cartoon_project_id": "cartoon-project"},
    }
    with patch("app.services.cartoon_job.run_cartoon_generation", new=AsyncMock()) as generate:
        await media_job._run(job, tmp_path)

    generate.assert_awaited_once_with(job, tmp_path, storage)


def test_cinematic_jannat_preset_locks_one_character_and_three_bedroom_scenes():
    storyboard = {
        "characters": [{"id": "different", "name": "Different"}],
        "scenes": [
            {"environment": "forest", "character_ids": ["different"], "speaker_id": "different"},
            {"environment": "city", "character_ids": ["different"], "speaker_id": "different"},
            {"environment": "school", "character_ids": ["different"], "speaker_id": "different"},
        ],
    }
    result = _apply_cinematic_jannat_storyboard(storyboard)
    assert len(result["characters"]) == 1
    character = result["characters"][0]
    assert character["id"] == "jannat"
    assert character["name"] == "Jannat"
    assert character["voice_type"] == "female"
    assert character["appearance"]["shirt_color"] == "#306b73"
    assert character["appearance"]["hair_color"] == "#121c29"
    assert all(scene["environment"] == "home" for scene in result["scenes"])
    assert all(scene["character_ids"] == ["jannat"] for scene in result["scenes"])
    assert all(scene["speaker_id"] == "jannat" for scene in result["scenes"])

    with pytest.raises(CartoonJobError) as error:
        _apply_cinematic_jannat_storyboard({"characters": [], "scenes": [{"id": "only-one"}]})
    assert error.value.category == "CARTOON_CINEMATIC_STORY_INVALID"

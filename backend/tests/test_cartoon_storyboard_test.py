import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import cartoon_studio as studio
from app.main import app
from app.services import cartoon_story_planner as planner
from story_v3_fixtures import fixtures


CSRF = {"X-CSRF-Token": "csrf-fixture"}
COOKIES = {"csrf_token": "csrf-fixture"}


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["nvidia", "openrouter"])
async def test_internal_storyboard_test_uses_the_selected_provider_and_returns_no_key(monkeypatch, provider):
    from app.services.auth import current_user

    user = {"id": "tester", "cartoon_studio_access_override": True}
    monkeypatch.setitem(app.dependency_overrides, current_user, lambda: user)
    monkeypatch.setattr(studio, "get_settings", lambda: SimpleNamespace(cartoon_storyboard_test_user_ids=" tester "))
    monkeypatch.setattr(studio, "fetch_one", AsyncMock(return_value=None))
    monkeypatch.setattr(studio, "consume_rate_limit", AsyncMock(return_value=True))
    saved_key = AsyncMock(return_value="sk-or-fake-saved-test-value")
    monkeypatch.setattr(studio, "_provider_key", saved_key)
    upstream = AsyncMock(return_value=httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(fixtures()["garden"])}}],
    }))

    async def request(key, payload, *, provider, timeout):
        return await upstream(key, payload, provider=provider, timeout=timeout)

    monkeypatch.setattr(studio, "request_storyboard", request)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                                 cookies=COOKIES, headers=CSRF) as client:
        discovery = await client.get("/api/v1/cartoon-studio/providers")
        assert discovery.json()["storyboard_test_enabled"] is True
        response = await client.post("/api/v1/cartoon-studio/storyboard-test", data={
            "prompt": "A fox finds the lost ball.", "provider": provider,
            "nvidia_key": "nvapi-fake-unique-test-value", "language": "en", "duration_seconds": "15",
        })
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert "fake-" not in response.text
    assert response.json()["storyboard"]["duration"] == 15
    key, payload = upstream.await_args.args
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert upstream.await_args.kwargs["provider"] == provider
    if provider == "nvidia":
        assert key == "nvapi-fake-unique-test-value"
        assert payload["model"] == planner.NVIDIA_STORY_MODEL
        assert isinstance(payload["messages"][1]["content"], str)
        assert "provider" not in payload
        saved_key.assert_not_called()
    else:
        assert key == "sk-or-fake-saved-test-value"
        assert payload["model"] == planner.STORY_MODEL
        assert payload["provider"] == {"require_parameters": True}
        saved_key.assert_awaited_once_with("tester")


@pytest.mark.asyncio
async def test_storyboard_test_denies_other_beta_accounts_even_with_a_valid_key(monkeypatch):
    from app.services.auth import current_user

    monkeypatch.setitem(app.dependency_overrides, current_user, lambda: {
        "id": "another-beta", "cartoon_studio_access_override": True,
    })
    monkeypatch.setattr(studio, "get_settings", lambda: SimpleNamespace(cartoon_storyboard_test_user_ids="tester"))
    request = AsyncMock()
    monkeypatch.setattr(studio, "request_storyboard", request)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                                 cookies=COOKIES, headers=CSRF) as client:
        response = await client.post("/api/v1/cartoon-studio/storyboard-test", data={
            "prompt": "A fox finds the lost ball.", "provider": "nvidia", "nvidia_key": "nvapi-fake-unique-test-value",
        })
    assert response.status_code == 403
    assert response.json()["detail"] == "Storyboard testing is not enabled for this account."
    assert "nvapi-" not in response.text
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_nvidia_key_is_sent_only_to_direct_nvidia_endpoint(monkeypatch):
    client_class = httpx.AsyncClient

    def send(request):
        assert str(request.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer nvapi-transport-test-only"
        payload = json.loads(request.content)
        assert payload["model"] == planner.NVIDIA_STORY_MODEL
        assert payload["stream"] is False
        assert "nvapi-" not in request.content.decode()
        return httpx.Response(200, json={"choices": []})

    monkeypatch.setattr(planner.httpx, "AsyncClient", lambda **kwargs:
                        client_class(transport=httpx.MockTransport(send), **kwargs))
    payload = planner.planner_payload("A fox finds a ball.", 15, "2d-cartoon", "en", provider="nvidia")
    assert (await planner.request_storyboard("nvapi-transport-test-only", payload, provider="nvidia")).is_success


@pytest.mark.asyncio
@pytest.mark.parametrize("selection,allowed,expected_status", [
    ("glm", False, 200), ("nemotron", False, 200), ("nvidia", True, 200),
    ("nvidia", False, 403), ("unexpected-model", True, 422),
])
async def test_project_creation_queues_selected_planner_without_exposing_keys(
    monkeypatch, selection, allowed, expected_status,
):
    from app.services.auth import current_user

    user = {"id": "tester", "cartoon_studio_access_override": True, "email_verified_at": "2026-01-01"}
    key = "nvapi-fake-unique-test-value"
    monkeypatch.setitem(app.dependency_overrides, current_user, lambda: user)
    monkeypatch.setattr("app.main.current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(studio, "_storyboard_test_allowed", lambda _: allowed)
    monkeypatch.setattr(studio, "_provider_key", AsyncMock(return_value="sk-or-fake-saved-test-value"))
    monkeypatch.setattr(studio, "_models", AsyncMock(return_value=[]))
    monkeypatch.setattr(studio, "consume_rate_limit", AsyncMock(return_value=True))
    monkeypatch.setattr(studio, "fetch_one", AsyncMock(return_value=None))
    monkeypatch.setattr(studio, "execute", execute := AsyncMock())
    monkeypatch.setattr(studio, "create_job", queue := AsyncMock(return_value="queued-job"))
    monkeypatch.setattr(studio, "dispatch_job", dispatch := AsyncMock())
    monkeypatch.setattr(studio, "_owned_project", AsyncMock(return_value={"id": "new-project"}))

    @asynccontextmanager
    async def lock(_name):
        yield

    monkeypatch.setattr(studio, "distributed_advisory_lock", lock)
    monkeypatch.setattr(studio, "request_storyboard", upstream := AsyncMock(return_value=httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(fixtures()["garden"])}}],
    })))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                                 cookies=COOKIES, headers=CSRF) as client:
        response = await client.post("/api/v1/cartoon-studio/projects", data={
            "prompt": "A fox finds the lost ball.", "story_planner": selection,
            "nvidia_key": key, "language": "ur", "duration_seconds": "15",
            "tts_model": "system/edge-tts-urdu",
        })
    assert response.status_code == expected_status, response.text
    assert key not in response.text
    if expected_status != 200:
        upstream.assert_not_awaited()
        execute.assert_not_awaited()
        dispatch.assert_not_awaited()
        return
    values = execute.await_args_list[0].args[1]
    assert values[8] == planner.PROJECT_STORY_MODELS[selection]
    queue.assert_awaited_once_with(user["id"], "cartoon_generate", payload={"cartoon_project_id": values[0]})
    dispatch.assert_awaited_once()
    assert key not in str(execute.await_args_list)
    if selection == "nvidia":
        upstream.assert_awaited_once()
        assert upstream.await_args.args[0] == key
        assert upstream.await_args.kwargs["provider"] == "nvidia"
        assert json.loads(values[10])["scenes"]
    else:
        upstream.assert_not_awaited()
        assert json.loads(values[10]) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("recovers", [True, False])
async def test_nvidia_create_corrects_timing_only_once(monkeypatch, recovers):
    prompt = "0–10 seconds Jannat wakes up. 10–20 seconds She remembers. 20–30 seconds She looks at the door."
    valid = fixtures()["jannat"]
    valid["scenes"].pop(1)
    merged = {**valid, "scenes": valid["scenes"][:2]}

    def reply(story):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(story)}}]})

    request = AsyncMock(side_effect=[reply(merged), reply(valid if recovers else merged)])
    monkeypatch.setattr(studio, "request_storyboard", request)
    args = ("nvapi-fixture", prompt, 30, "2d-cartoon", "ur", "nvidia")
    if recovers:
        story = await studio._plan_in_request(*args, repair_timing=True)
        assert [scene["start"] for scene in story["scenes"]] == [0, 10, 20]
    else:
        with pytest.raises(studio.HTTPException, match="No video was queued"):
            await studio._plan_in_request(*args, repair_timing=True)

    first, second = request.await_args_list
    assert first.kwargs["timeout"] + second.kwargs["timeout"] == 105
    assert first.args[0] == second.args[0] == args[0]
    assert first.args[1]["messages"][1] == second.args[1]["messages"][1]
    assert "first storyboard was rejected" in second.args[1]["messages"][0]["content"]


def test_scripted_ranges_survive_both_planners_and_combined_scenes_are_rejected():
    prompt = "0–10 seconds Jannat wakes up. 10–20 seconds She remembers. 20–30 seconds She looks at the door."
    raw = fixtures()["jannat"]
    raw["scenes"].pop(1)

    def response():
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(raw)}}],
        })
    for provider in ("nvidia", "openrouter"):
        payload = planner.planner_payload(prompt, 30, "2d-cartoon", "ur", provider=provider)
        assert "durations [10, 10, 10]" in str(payload["messages"][-1]["content"])
    story = planner.parse_storyboard_reply(response(), prompt=prompt, duration=30)
    assert [(scene["start"], scene["duration"]) for scene in story["scenes"]] == [(0, 10), (10, 10), (20, 10)]
    raw["scenes"].pop(1)
    with pytest.raises(planner.StoryboardReplyError) as failure:
        planner.parse_storyboard_reply(response(), prompt=prompt, duration=30)
    assert failure.value.category == "CARTOON_STORY_BEAT_TIMING"


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", ["glm", "nemotron", "nvidia"])
async def test_worker_uses_selected_model_and_passes_story_to_existing_renderer(monkeypatch, tmp_path, selection):
    from app.services import cartoon_job as worker, cartoon_story_job as director

    model = planner.PROJECT_STORY_MODELS[selection]
    raw = fixtures()["garden"]
    storyboard = planner.normalize_director_story(raw, duration=15)
    project = {
        "id": "cartoon", "status": "queued", "language": "ur", "style": "2d-cartoon",
        "prompt": "A fox finds the lost ball.", "duration_seconds": 15, "text_model": model,
        "tts_model": "system/edge-tts-urdu", "assets_json": "{}",
        "storyboard_json": json.dumps(storyboard if selection == "nvidia" else {}),
    }
    monkeypatch.setattr(worker, "fetch_one", AsyncMock(side_effect=[project, {"api_key_ciphertext": "fixture"}]))
    monkeypatch.setattr(worker, "decrypt_provider_key", lambda _: "test-openrouter-key")
    monkeypatch.setattr(worker, "execute", AsyncMock())
    monkeypatch.setattr(worker, "update_job", AsyncMock())
    monkeypatch.setattr(worker, "_openrouter_models", AsyncMock(return_value=[]))
    monkeypatch.setattr(worker, "_extract_reference_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(worker, "request_storyboard", upstream := AsyncMock(return_value=httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(raw)}}],
    })))
    monkeypatch.setattr(director, "run_director_job", render := AsyncMock())
    job = {"id": "job", "user_id": "tester", "payload": {"cartoon_project_id": "cartoon"}}
    storage = object()
    await worker.run_cartoon_generation(job, tmp_path, storage)

    render.assert_awaited_once()
    assert render.await_args.args[2]["scenes"] == storyboard["scenes"]
    assert render.await_args.args[-3:] == (storage, "test-openrouter-key", "system/edge-tts-urdu")
    if selection == "nvidia":
        upstream.assert_not_awaited()
    else:
        upstream.assert_awaited_once()
        key, payload = upstream.await_args.args
        assert (key, payload["model"], upstream.await_args.kwargs["provider"]) == ("test-openrouter-key", model, "openrouter")

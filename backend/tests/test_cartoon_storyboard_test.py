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
async def test_postgres_nvidia_key_saving_waits_for_credential_migration(monkeypatch):
    monkeypatch.setattr(studio, "get_settings", lambda: SimpleNamespace(normalized_database_backend="postgres"))
    revision = AsyncMock(return_value={"version_num": "20261121_14"})
    monkeypatch.setattr(studio, "fetch_one", revision)
    assert not await studio._nvidia_storage_ready()
    revision.return_value = {"version_num": studio.POSTGRES_SCHEMA_REVISION}
    assert await studio._nvidia_storage_ready()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["nvidia", "openrouter"])
async def test_internal_storyboard_test_uses_the_selected_provider_and_returns_no_key(monkeypatch, provider):
    from app.services.auth import current_user

    user = {"id": "tester", "cartoon_studio_access_override": True}
    monkeypatch.setitem(app.dependency_overrides, current_user, lambda: user)
    monkeypatch.setattr(studio, "get_settings", lambda: SimpleNamespace(
        cartoon_storyboard_test_user_ids=" tester ", normalized_database_backend="sqlite",
    ))
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
        assert payload["reasoning_effort"] == "none"
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
    ("glm", False, 200), ("free", False, 200), ("nemotron", False, 422), ("nvidia", True, 200),
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
    monkeypatch.setattr(studio, "consume_rate_limit", previous_creation_cap := AsyncMock(return_value=False))
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
            "tts_model": "hexgrad/kokoro-82m" if selection == "free" else "system/edge-tts-urdu",
            "voice_id": "hf_alpha" if selection == "free" else "",
        })
    assert response.status_code == expected_status, response.text
    previous_creation_cap.assert_not_awaited()
    assert key not in response.text
    if expected_status != 200:
        upstream.assert_not_awaited()
        execute.assert_not_awaited()
        dispatch.assert_not_awaited()
        return
    values = execute.await_args_list[0].args[1]
    assert values[8] == planner.PROJECT_STORY_MODELS[selection]
    assert values[9] == "system/edge-tts-urdu"
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
@pytest.mark.parametrize("in_worker", [True, False])
async def test_nvidia_create_corrects_timing_only_once(monkeypatch, recovers, in_worker):
    from app.services import cartoon_job as worker

    prompt = "0–10 seconds Jannat wakes up. 10–20 seconds She remembers. 20–30 seconds She looks at the door."
    valid = fixtures()["jannat"]
    valid["scenes"].pop(1)
    merged = {**valid, "scenes": valid["scenes"][:2]}

    def reply(story):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(story)}}]})

    request = AsyncMock(side_effect=[reply(merged), reply(valid if recovers else merged)])
    if in_worker:
        monkeypatch.setattr(worker, "request_storyboard", request)
        invoke = lambda: worker._generate_storyboard("nvapi-fixture", prompt, 30, "2d-cartoon", "ur", [], provider="nvidia")
        expected_error = worker.CartoonJobError
    else:
        monkeypatch.setattr(studio, "request_storyboard", request)
        invoke = lambda: studio._plan_in_request("nvapi-fixture", prompt, 30, "2d-cartoon", "ur", "nvidia", repair_timing=True)
        expected_error = studio.HTTPException
    if recovers:
        story = await invoke()
        assert [scene["start"] for scene in story["scenes"]] == [0, 10, 20]
    else:
        with pytest.raises(expected_error, match="wrong number of scenes|combined or split"):
            await invoke()

    first, second = request.await_args_list
    if in_worker:
        assert first.kwargs["timeout"] == second.kwargs["timeout"] == 105
    else:
        assert first.kwargs["timeout"] + second.kwargs["timeout"] == 105
    assert first.args[0] == second.args[0] == "nvapi-fixture"
    assert first.args[1]["messages"][1] == second.args[1]["messages"][1]
    assert "first storyboard was rejected" in second.args[1]["messages"][0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "first_failure", "second_failure", "attempts", "error_category"),
    [
        ("nvidia", TimeoutError(), None, 2, None),
        ("nvidia", httpx.ReadError("connection lost"), None, 2, None),
        ("nvidia", httpx.Response(503), None, 2, None),
        ("nvidia", TimeoutError(), TimeoutError(), 2, "CARTOON_PROVIDER_TEMPORARY"),
        ("nvidia", httpx.Response(401), None, 1, "CARTOON_PROVIDER_AUTH"),
        ("nvidia", httpx.Response(429), None, 1, "CARTOON_PROVIDER_RATE_LIMIT"),
        ("openrouter", TimeoutError(), None, 1, "CARTOON_PROVIDER_TEMPORARY"),
    ],
)
async def test_worker_only_retries_transient_nvidia_planning_failures(
    monkeypatch, provider, first_failure, second_failure, attempts, error_category,
):
    from app.services import cartoon_job as worker

    response = httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(fixtures()["garden"])}}],
    })
    request = AsyncMock(side_effect=[first_failure, second_failure or response])
    monkeypatch.setattr(worker, "request_storyboard", request)
    pause = AsyncMock()
    monkeypatch.setattr(worker.asyncio, "sleep", pause)

    async def generate():
        return await worker._generate_storyboard(
            "fixture-key", "A fox finds the lost ball.", 15, "2d-cartoon", "en", [], provider=provider,
        )

    if error_category:
        with pytest.raises(worker.CartoonJobError) as error:
            await generate()
        assert error.value.category == error_category
    else:
        assert (await generate())["scenes"]
    assert request.await_count == attempts
    if attempts == 2:
        assert request.await_args_list[0] == request.await_args_list[1]
        pause.assert_awaited_once_with(1)
    else:
        pause.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("recovers", [True, False])
async def test_nvidia_truncation_replans_the_same_timed_script_with_a_smaller_schema(monkeypatch, recovers):
    from app.services import cartoon_job as worker

    prompt = (
        "The Wind Stole My Hat. 0–10 seconds Nora loses her hat. "
        "10–20 seconds Nora finds a shivering dog. 20–30 seconds Nora shares the hat."
    )
    truncated = httpx.Response(200, json={
        "choices": [{"finish_reason": "length", "message": {"content": '{"scenes":['}}],
        "usage": {"completion_tokens": 16384, "completion_tokens_details": {"reasoning_tokens": 0}},
    })
    story = fixtures()["jannat"]
    story["scenes"].pop(1)
    completed = httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(story)}}],
    })
    request = AsyncMock(side_effect=[truncated, completed if recovers else truncated])
    monkeypatch.setattr(worker, "request_storyboard", request)

    async def generate():
        return await worker._generate_storyboard("nvapi-fixture", prompt, 30, "2d-cartoon", "en", [], provider="nvidia")

    if recovers:
        result = await generate()
        assert [(scene["start"], scene["duration"]) for scene in result["scenes"]] == [(0, 10), (10, 10), (20, 10)]
    else:
        with pytest.raises(worker.CartoonJobError) as error:
            await generate()
        assert error.value.category == "CARTOON_STORY_TRUNCATED"

    first, second = (call.args[1] for call in request.await_args_list)
    scenes, compact_scenes = (
        payload["response_format"]["json_schema"]["schema"]["properties"]["scenes"]
        for payload in (first, second)
    )
    assert scenes["minItems"] == scenes["maxItems"] == compact_scenes["maxItems"] == 3
    assert scenes["items"]["properties"]["actions"]["maxItems"] == 14
    assert compact_scenes["items"]["properties"]["actions"]["maxItems"] == 8
    assert first["messages"][1] == second["messages"][1]
    assert first["model"] == second["model"] == planner.NVIDIA_STORY_MODEL
    assert "exceeded the output budget" in second["messages"][0]["content"]


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
@pytest.mark.parametrize("model", [planner.STORY_MODEL, planner.FREE_STORY_MODEL])
async def test_openrouter_repairs_a_bad_storyboard_with_the_same_model(monkeypatch, model):
    from app.services import cartoon_job as worker

    response = httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(fixtures()["garden"])}}],
    })
    incomplete = httpx.Response(200, json={
        "choices": [{"finish_reason": "length", "message": {"content": '{"scenes":['}}],
    })
    request = AsyncMock(side_effect=[incomplete, response])
    monkeypatch.setattr(worker, "request_storyboard", request)

    result = await worker._generate_storyboard(
        "fixture-key", "A fox finds the lost ball.", 15, "2d-cartoon", "en", [], model=model,
    )

    assert result["scenes"]
    first, second = (call.args[1] for call in request.await_args_list)
    assert first["model"] == second["model"] == model
    assert first["messages"][1] == second["messages"][1]
    assert "exceeded the output budget" in second["messages"][0]["content"]
    assert all("models" not in call.args[1] for call in request.await_args_list)


def test_storyboard_repairs_a_box_opening_mislabeled_on_a_book():
    story = fixtures()["library"]
    scene = story["scenes"][0]
    scene["actions"].append({
        "type": "open_box", "character_id": "mira", "target_id": "book", "start": 4, "end": 5,
    })
    response = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(story)}}]})
    result = planner.parse_storyboard_reply(response, prompt="Mira opens the book.", duration=15)
    action = next(action for action in result["scenes"][0]["actions"] if action["type"] == "open_book")
    assert action["target_id"] == "book"
    assert all(prop["type"] != "box" for prop in result["scenes"][0]["props"])


@pytest.mark.asyncio
@pytest.mark.parametrize("visible_speak_cue", [True, False])
async def test_nvidia_recovers_dialogue_assigned_to_narrator(monkeypatch, visible_speak_cue):
    from copy import deepcopy
    from app.services import cartoon_job as worker

    corrected = fixtures()["library"]
    lines = corrected["scenes"][0]["speech"]
    lines[1]["text"] = "Surprise!"
    invalid = deepcopy(corrected)
    scene = invalid["scenes"][0]
    scene["speech"][1]["speaker_id"] = "narrator"
    if visible_speak_cue:
        scene["actions"].append({"type": "speak", "character_id": "arun", "start": 3, "end": 4})

    def reply(story):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(story)}}]})

    upstream = AsyncMock(side_effect=[reply(invalid), reply(corrected)])
    monkeypatch.setattr(worker, "request_storyboard", upstream)
    result = await worker._generate_storyboard(
        "nvapi-fixture", "Mira reads a book, then Arun says “Surprise!”", 15, "2d-cartoon", "en", [],
        provider="nvidia",
    )
    line = result["scenes"][0]["speech"][1]
    assert (line["speaker_id"], line["track"], line["text"]) == ("arun", "dialogue", "Surprise!")
    assert upstream.await_count == (1 if visible_speak_cue else 2)
    if not visible_speak_cue:
        original, correction = (call.args[1]["messages"] for call in upstream.await_args_list)
        assert original[1] == correction[1]
        assert "dialogue speaker was not visible" in correction[0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", ["free", "glm", "nvidia", "preset-nvidia", "legacy-hosted"])
async def test_worker_uses_selected_model_and_passes_story_to_existing_renderer(monkeypatch, tmp_path, selection):
    from app.services import cartoon_job as worker, cartoon_story_job as director

    model = ("nvidia/nemotron-3.5-super-vl" if selection == "legacy-hosted"
             else planner.PROJECT_STORY_MODELS["nvidia" if selection == "preset-nvidia" else selection])
    raw = fixtures()["garden"]
    storyboard = planner.normalize_director_story(raw, duration=15)
    project = {
        "id": "cartoon", "status": "queued", "language": "ur", "style": "2d-cartoon",
        "prompt": "A fox finds the lost ball.", "duration_seconds": 15, "text_model": model,
        "tts_model": "hexgrad/kokoro-82m" if selection == "preset-nvidia" else "system/edge-tts-urdu",
        "assets_json": json.dumps({"_preferred_voice": "hf_alpha"}),
        "storyboard_json": json.dumps(storyboard if selection == "preset-nvidia" else {}),
    }
    credentials = [{"api_key_ciphertext": "test-openrouter-key"}, {"api_key_ciphertext": "test-nvidia-key"}]
    monkeypatch.setattr(worker, "fetch_one", fetch := AsyncMock(side_effect=[project, *credentials]))
    monkeypatch.setattr(worker, "decrypt_provider_key", lambda value: value)
    monkeypatch.setattr(worker, "execute", AsyncMock())
    monkeypatch.setattr(worker, "update_job", AsyncMock())
    monkeypatch.setattr(worker, "_openrouter_models", voice_catalog := AsyncMock(return_value=[]))
    monkeypatch.setattr(worker, "_extract_reference_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(worker, "request_storyboard", upstream := AsyncMock(return_value=httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(raw)}}],
    })))
    monkeypatch.setattr(director, "run_director_job", render := AsyncMock())
    job = {"id": "job", "user_id": "tester", "payload": {"cartoon_project_id": "cartoon"}}
    storage = object()
    if selection == "legacy-hosted":
        with pytest.raises(worker.CartoonJobError, match="older story planner"):
            await worker.run_cartoon_generation(job, tmp_path, storage)
        upstream.assert_not_awaited()
        render.assert_not_awaited()
        return
    await worker.run_cartoon_generation(job, tmp_path, storage)

    render.assert_awaited_once()
    assert render.await_args.args[2]["scenes"] == storyboard["scenes"]
    assert render.await_args.args[-3:] == (storage, "test-openrouter-key", "system/edge-tts-urdu")
    voice_catalog.assert_not_awaited()
    assert render.await_args.args[2]["characters"][0]["voice_id"] in {"ur-PK-UzmaNeural", "ur-PK-AsadNeural"}
    if selection == "preset-nvidia":
        upstream.assert_not_awaited()
    else:
        upstream.assert_awaited_once()
        key, payload = upstream.await_args.args
        expected = "nvidia" if selection == "nvidia" else "openrouter"
        assert (key, payload["model"], upstream.await_args.kwargs["provider"]) == (f"test-{expected}-key", model, expected)
        assert fetch.await_args.args[1] == (job["user_id"], expected)

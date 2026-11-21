import json
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

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import get_settings
from app.services.hinglish_stage1_routing import (
    ELEVENLABS_ROMAN_ROUTE,
    LEGACY_ROUTE,
    persisted_stage1_route,
    resolve_stage1_route,
)


def _stage1(settings, monkeypatch, enabled=True, users="user-a"):
    monkeypatch.setattr(settings, "hinglish_stage1_enabled", enabled)
    monkeypatch.setattr(settings, "hinglish_stage1_user_ids", users)


def test_stage1_language_matrix_and_disabled_fail_closed(monkeypatch):
    settings = get_settings()
    _stage1(settings, monkeypatch)
    for language in ("hinglish", "roman_hinglish"):
        assert resolve_stage1_route(language, "user-a")["asr_route"] == ELEVENLABS_ROMAN_ROUTE
    for language in ("hi", "mr", "en", "auto", ""):
        assert resolve_stage1_route(language, "user-a")["asr_route"] == LEGACY_ROUTE
    _stage1(settings, monkeypatch, enabled=False)
    assert resolve_stage1_route("hinglish", "user-a")["asr_route"] == LEGACY_ROUTE


def test_allowlist_exact_match_malformed_and_client_injection_fail_closed(monkeypatch):
    settings = get_settings()
    _stage1(settings, monkeypatch, users="user-a, !!!, user-a-extra")
    assert resolve_stage1_route("hinglish", "user")["asr_route"] == LEGACY_ROUTE
    assert resolve_stage1_route("hinglish", "user-a-extra")["asr_route"] == ELEVENLABS_ROMAN_ROUTE
    # The resolver receives only server-authenticated identity; a request body
    # cannot supply a different identity to this API.
    assert resolve_stage1_route("hinglish", "user-b")["asr_route"] == LEGACY_ROUTE
    _stage1(settings, monkeypatch, users="")
    assert resolve_stage1_route("hinglish", "user-a")["asr_route"] == LEGACY_ROUTE


def test_persisted_payload_is_toctou_safe_and_old_payloads_fail_closed(monkeypatch):
    settings = get_settings()
    _stage1(settings, monkeypatch, users="user-a")
    allowlisted_payload = resolve_stage1_route("hinglish", "user-a")
    _stage1(settings, monkeypatch, users="")  # allowlist changed before worker/restart
    assert persisted_stage1_route(allowlisted_payload)["asr_route"] == ELEVENLABS_ROMAN_ROUTE

    legacy_payload = resolve_stage1_route("hinglish", "user-b")
    _stage1(settings, monkeypatch, users="user-b")  # newly allowed after enqueue
    assert persisted_stage1_route(legacy_payload)["asr_route"] == LEGACY_ROUTE
    assert persisted_stage1_route({})["asr_route"] == LEGACY_ROUTE
    assert persisted_stage1_route({"asr_route": None})["asr_route"] == LEGACY_ROUTE
    assert persisted_stage1_route({"asr_route": "unknown"})["asr_route"] == LEGACY_ROUTE


def test_provider_selection_uses_persisted_route_not_current_flags(monkeypatch, tmp_path):
    from app.services import asr_providers
    from app.services.asr_providers import ASRResult

    async def elevenlabs(*args, **kwargs):
        return ASRResult("elevenlabs", "scribe_v2", "hi", None, "text", [], [], 1, .01, 1)

    async def legacy(*args, **kwargs):
        return ASRResult("groq", "whisper-large-v3", "hi", None, "text", [], [], 1, .01, 1)

    monkeypatch.setattr(asr_providers, "_transcribe_elevenlabs_hinglish", elevenlabs)
    monkeypatch.setattr(asr_providers, "_transcribe_legacy_api", legacy)
    assert asyncio.run(asr_providers.transcribe_api(tmp_path / "a.flac", language_hint="hinglish", duration=1, asr_route=ELEVENLABS_ROMAN_ROUTE)).provider == "elevenlabs"
    assert asyncio.run(asr_providers.transcribe_api(tmp_path / "b.flac", language_hint="hinglish", duration=1, asr_route=LEGACY_ROUTE)).provider == "groq"


def test_worker_reconstructs_route_from_payload_without_allowlist(monkeypatch):
    from app import worker

    route_seen = []

    async def process(job_id, project_id, video_id, user, asr_route="legacy", force_transcribe=False):
        route_seen.append(asr_route)

    job = {"id": "job-a", "kind": "process_video", "project_id": "project-a", "user_id": "user-a", "payload": {"video_id": "video-a", "asr_route": ELEVENLABS_ROMAN_ROUTE, "hinglish_rollout_stage": "stage1"}}
    with patch("app.worker.fetch_one", new=AsyncMock(side_effect=[{"id": "user-a"}, {"id": "video-a", "project_id": "project-a"}])), patch("app.worker.release_claim", new=AsyncMock()), patch("app.api.routes._process_project", new=process):
        asyncio.run(worker.run_claimed_job(job))
    assert route_seen == [ELEVENLABS_ROMAN_ROUTE]

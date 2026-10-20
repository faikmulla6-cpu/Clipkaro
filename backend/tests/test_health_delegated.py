"""API liveness must not require FFmpeg in the separate Modal API image."""
from types import SimpleNamespace

import pytest

from app.api import routes
from app.services import video


@pytest.mark.asyncio
async def test_modal_api_is_healthy_when_ffmpeg_is_delegated(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(production_serverless_mode=True))
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)
    result = await routes.health()
    assert result["status"] == "healthy"
    assert result["ffmpeg"] is False
    assert result["media_processing"] == "delegated"


@pytest.mark.asyncio
async def test_local_api_is_degraded_without_media_tools(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(production_serverless_mode=False))
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)
    result = await routes.health()
    assert result["status"] == "degraded"
    assert result["ffmpeg"] is False
    assert result["media_processing"] == "local"


@pytest.mark.asyncio
async def test_local_api_is_healthy_with_media_tools(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(production_serverless_mode=False))
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    result = await routes.health()
    assert result["status"] == "healthy"
    assert result["ffmpeg"] is True

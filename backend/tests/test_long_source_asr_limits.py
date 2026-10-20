"""Long paid source duration must reach bounded API transcription, not fail at 60m."""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services import transcription


class _ReachedChunks(Exception):
    pass


@pytest.mark.parametrize("minutes", [90, 180, 240])
@pytest.mark.asyncio
async def test_paid_long_source_reaches_api_chunking(minutes, monkeypatch, tmp_path):
    cfg = Settings(_env_file=None)
    assert cfg.asr_api_max_audio_minutes >= minutes
    async def pretend_extract(source, audio):
        pass
    async def duration(audio):
        return minutes * 60.0
    async def reached(audio, *, duration, output_dir, chunk_seconds,
                      overlap_seconds, max_chunks, max_bytes):
        assert duration == minutes * 60.0
        assert max_chunks >= math.ceil((duration - overlap_seconds) /
                                      (chunk_seconds - overlap_seconds))
        raise _ReachedChunks()
    monkeypatch.setattr(transcription, "get_settings", lambda: cfg)
    monkeypatch.setattr(transcription, "extract_api_audio", pretend_extract)
    monkeypatch.setattr(transcription, "probe_audio_duration", duration)
    monkeypatch.setattr(transcription, "detect_speech_regions", lambda audio: [(0, 60)])
    monkeypatch.setattr(transcription, "chunk_api_audio", reached)
    with pytest.raises(_ReachedChunks):
        await transcription._transcribe_api_impl(tmp_path / "long-video.mp4", "auto")


@pytest.mark.asyncio
async def test_sources_exceeding_agency_ceiling_still_fail_closed(monkeypatch, tmp_path):
    cfg = Settings(_env_file=None)
    async def noop(source, audio):
        pass
    async def too_long(audio):
        return (cfg.asr_api_max_audio_minutes + 1) * 60.0
    monkeypatch.setattr(transcription, "get_settings", lambda: cfg)
    monkeypatch.setattr(transcription, "extract_api_audio", noop)
    monkeypatch.setattr(transcription, "probe_audio_duration", too_long)
    with pytest.raises(RuntimeError, match="API ASR limit"):
        await transcription._transcribe_api_impl(tmp_path / "oversized.mp4", "auto")


def test_chunk_budget_includes_stage_one_candidate():
    cfg = Settings(_env_file=None)
    total_seconds = cfg.asr_api_max_audio_minutes * 60
    for span in (cfg.asr_chunk_seconds, cfg.elevenlabs_asr_chunk_seconds):
        assert cfg.asr_api_max_chunks >= math.ceil(
            (total_seconds - cfg.asr_chunk_overlap_seconds) /
            (span - cfg.asr_chunk_overlap_seconds)
        )
    assert cfg.asr_api_max_audio_minutes == 240

def test_plan_video_ceiling_never_exceeds_transcription_ceiling():
    from app.api.routes import PLAN_MAX_SOURCE_MINUTES
    cfg = Settings(_env_file=None)
    assert max(PLAN_MAX_SOURCE_MINUTES.values()) <= cfg.asr_api_max_audio_minutes
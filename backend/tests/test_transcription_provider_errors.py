import asyncio
from pathlib import Path

import pytest

from app.services.asr_providers import ASRProviderError
from app.services import transcription


def test_api_auth_failure_is_not_misreported_as_transient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A rejected server credential must be actionable without exposing it."""

    async def fake_extract(_video: Path, audio: Path) -> None:
        audio.write_bytes(b"audio")

    async def fake_duration(_audio: Path) -> float:
        return 1.0

    async def fake_chunks(*_args, **_kwargs):
        return [(tmp_path / "chunk.flac", 0.0, 1.0)]

    async def rejected(*_args, **_kwargs):
        raise ASRProviderError("ElevenLabs rejected the transcription request", status_code=401)

    monkeypatch.setattr(transcription, "extract_api_audio", fake_extract)
    monkeypatch.setattr(transcription, "probe_audio_duration", fake_duration)
    monkeypatch.setattr(transcription, "chunk_api_audio", fake_chunks)
    monkeypatch.setattr(transcription, "transcribe_api", rejected)

    with pytest.raises(RuntimeError, match="administrator attention"):
        asyncio.run(transcription._transcribe_api_impl(tmp_path / "source.mp4", "hinglish", asr_route="elevenlabs_roman"))

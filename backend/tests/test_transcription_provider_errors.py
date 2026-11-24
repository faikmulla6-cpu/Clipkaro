import asyncio
from pathlib import Path

import pytest

from app.services import asr_providers, transcription
from app.services.asr_providers import ASRProviderError


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
    monkeypatch.setattr(transcription, "detect_speech_regions", lambda _audio: [{"start": 0.0, "end": 1.0}])
    monkeypatch.setattr(transcription, "chunk_api_audio", fake_chunks)
    monkeypatch.setattr(transcription, "transcribe_api", rejected)

    with pytest.raises(RuntimeError, match="administrator attention"):
        asyncio.run(transcription._transcribe_api_impl(tmp_path / "source.mp4", "hinglish", asr_route="elevenlabs_roman"))


def test_auto_hindi_foreign_script_retries_with_explicit_hindi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_extract(_video: Path, audio: Path) -> None:
        audio.write_bytes(b"audio")

    async def fake_duration(_audio: Path) -> float:
        return 30.0

    async def fake_chunks(audio: Path, **_kwargs):
        return [(audio, 0.0, 30.0)]

    hints: list[str] = []

    async def fake_transcribe(_audio: Path, *, language_hint: str, duration: float, **_kwargs):
        hints.append(language_hint)
        if language_hint == "hi":
            text = "यह एक साफ हिंदी वाक्य है जो सही तरीके से बोला गया है"
            words = [{"start": i * 2.0, "end": i * 2.0 + 1.0, "word": word} for i, word in enumerate(text.split())]
            return asr_providers._normalise({"language": "hi", "text": text, "segments": [{"start": 0, "end": 25, "text": text, "words": words}]}, "groq", "model", duration, .1, 1)
        text = "یہ ایک واضح ہندی جملہ ہے جو غلط رسم الخط میں آیا"
        words = [{"start": i * 2.0, "end": i * 2.0 + 1.0, "word": word} for i, word in enumerate(text.split())]
        return asr_providers._normalise({"language": "ur", "text": text, "segments": [{"start": 0, "end": 25, "text": text, "words": words}]}, "groq", "model", duration, .1, 1)

    monkeypatch.setattr(transcription, "extract_api_audio", fake_extract)
    monkeypatch.setattr(transcription, "probe_audio_duration", fake_duration)
    monkeypatch.setattr(transcription, "detect_speech_regions", lambda _audio: [{"start": 0.0, "end": 30.0}])
    monkeypatch.setattr(transcription, "chunk_api_audio", fake_chunks)
    monkeypatch.setattr(transcription, "transcribe_api", fake_transcribe)
    language, segments = asyncio.run(transcription._transcribe_api_impl(tmp_path / "source.mp4", "auto"))
    assert language == "hi" and segments
    assert hints == ["auto", "hi"]


@pytest.mark.asyncio
async def test_generated_cartoon_line_uses_api_timestamps_below_source_minimum(monkeypatch, tmp_path):
    from shutil import copyfile
    from unittest.mock import AsyncMock
    from app.services.cartoon_story_job import audio_alignment

    fixture = Path(__file__).resolve().parents[1] / "cartoon_engine/fixtures/story-v3/audio/library-scene-1-line-1.mp3"
    audio = tmp_path / "dialogue.mp3"
    copyfile(fixture, audio)
    settings = transcription.get_settings().model_copy(
        update={"transcription_backend": "faster-whisper", "asr_mode": "api"}
    )
    monkeypatch.setattr(transcription, "get_settings", lambda: settings)
    words = [
        {"word": "अरुण", "start": .2, "end": .7},
        {"word": "देखो", "start": .8, "end": 1.3},
    ]
    segments = [{"start": .2, "end": 1.3, "text": "अरुण देखो", "words": words}]
    response = asr_providers._normalise(
        {"language": "hi", "text": "अरुण देखो", "segments": segments},
        "groq", "fixture", 3, .1, 1,
    )
    provider = AsyncMock(return_value=response)
    monkeypatch.setattr(transcription, "transcribe_api", provider)

    with pytest.raises(RuntimeError, match="too little|quality verification"):
        await transcription.transcribe(audio, language_hint="hi")
    boundaries = await audio_alignment(audio, "hinglish")
    assert [word["offset"] for word in boundaries] == [2_000_000, 8_000_000]
    assert all(word["text"].isascii() for word in boundaries)
    assert provider.await_count == 2
    assert not audio.with_suffix(".asr.flac").exists()

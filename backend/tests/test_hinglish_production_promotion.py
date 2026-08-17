import asyncio
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services import asr_providers
from app.services.asr_providers import ASRProviderError, ASRResult
from app.services.hinglish_roman_pipeline import apply_roman_v3_display_v1, roman_caption_has_devanagari, verify_frozen_policies


def _result(provider: str = "elevenlabs") -> ASRResult:
    return ASRResult(provider, "scribe_v2", "hi", None, "आज meeting", [
        {"start": .01, "end": 1.02, "text": "आज meeting", "words": [
            {"start": .01, "end": .40, "text": "आज"}, {"start": .45, "end": 1.02, "text": "meeting"}
        ]}
    ], [], 1.02, .01, 1)


def test_frozen_roman_pipeline_preserves_native_timing_and_applies_once():
    rows = _result().segments
    output = apply_roman_v3_display_v1(rows)
    assert verify_frozen_policies()
    assert output[0]["words"][0]["start"] == .01
    assert output[0]["words"][0]["timing_source"] == "ELEVENLABS_NATIVE_WORD"
    assert not roman_caption_has_devanagari(output)
    assert output[0]["roman_v3_applied"] and output[0]["display_v1_applied"]
    with pytest.raises(RuntimeError, match="only once"):
        apply_roman_v3_display_v1(output)


def test_legacy_rollback_route_is_available(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "hinglish_asr_provider", "legacy")
    monkeypatch.setattr(settings, "roman_hinglish_enabled", False)
    assert settings.normalized_hinglish_asr_provider == "legacy"
    assert not settings.hinglish_roman_pipeline_enabled


def test_enabled_hinglish_selects_elevenlabs_without_legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = get_settings()
    monkeypatch.setattr(settings, "hinglish_asr_provider", "elevenlabs")
    monkeypatch.setattr(settings, "roman_hinglish_enabled", True)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-only")
    async def candidate(*args, **kwargs): return _result()
    async def legacy(*args, **kwargs): raise AssertionError("legacy route should not run after candidate success")
    monkeypatch.setattr(asr_providers, "_transcribe_elevenlabs_hinglish", candidate)
    monkeypatch.setattr(asr_providers, "_transcribe_legacy_api", legacy)
    result = asyncio.run(asr_providers.transcribe_api(tmp_path / "audio.flac", language_hint="hinglish", duration=1, asr_route="elevenlabs_roman"))
    assert result.provider == "elevenlabs"


def test_retriable_elevenlabs_failure_uses_legacy_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = get_settings()
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-only")
    monkeypatch.setattr(settings, "asr_provider_max_attempts", 1)
    class Broken:
        def __init__(self, *args, **kwargs): pass
        async def transcribe(self, *args, **kwargs): raise ASRProviderError("ElevenLabs request timed out", retryable=True)
    async def legacy(*args, **kwargs): return _result("groq")
    monkeypatch.setattr("app.services.candidate_asr_providers.ElevenLabsScribeV2Provider", Broken)
    monkeypatch.setattr(asr_providers, "_transcribe_legacy_api", legacy)
    result = asyncio.run(asr_providers._transcribe_elevenlabs_hinglish(tmp_path / "audio.flac", language_hint="hinglish", duration=1))
    assert result.provider == "groq" and result.fallback_used
    assert result.metadata["fallback_reason"] == "timeout"


def test_elevenlabs_rotates_to_next_private_key_only_after_rate_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = get_settings()
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    monkeypatch.setattr(settings, "elevenlabs_api_keys", "first-key,second-key")
    monkeypatch.setattr(settings, "asr_provider_max_attempts", 2)
    used: list[str] = []

    class RateLimitedThenReady:
        def __init__(self, key, *args, **kwargs):
            used.append(key)

        async def transcribe(self, *args, **kwargs):
            if len(used) == 1:
                raise ASRProviderError("ElevenLabs rate limit", retryable=True, rate_limited=True, status_code=429)
            result = _result()
            result.words = result.segments[0]["words"]
            return result

    monkeypatch.setattr("app.services.candidate_asr_providers.ElevenLabsScribeV2Provider", RateLimitedThenReady)
    result = asyncio.run(asr_providers._transcribe_elevenlabs_hinglish(tmp_path / "audio.flac", language_hint="hinglish", duration=1))
    assert result.provider == "elevenlabs"
    assert used == ["first-key", "second-key"]


def test_legacy_comma_separated_elevenlabs_key_setting_is_a_rotation_pool(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "elevenlabs_api_keys", "")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "first-key, second-key, first-key")
    assert settings.elevenlabs_keys == ["first-key", "second-key"]


def test_nonretriable_elevenlabs_error_does_not_spend_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = get_settings()
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-only")
    class Broken:
        def __init__(self, *args, **kwargs): pass
        async def transcribe(self, *args, **kwargs): raise ASRProviderError("ElevenLabs rejected the transcription request", status_code=401)
    async def legacy(*args, **kwargs): raise AssertionError("auth failure must not fallback")
    monkeypatch.setattr("app.services.candidate_asr_providers.ElevenLabsScribeV2Provider", Broken)
    monkeypatch.setattr(asr_providers, "_transcribe_legacy_api", legacy)
    with pytest.raises(ASRProviderError):
        asyncio.run(asr_providers._transcribe_elevenlabs_hinglish(tmp_path / "audio.flac", language_hint="hinglish", duration=1))

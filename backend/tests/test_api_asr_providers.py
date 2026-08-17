import asyncio
from pathlib import Path

import pytest
import httpx

from app.core.config import get_settings
from app.services import asr_providers

BACKEND_ROOT = Path(__file__).resolve().parents[1]

def _source(relative: str) -> str:
    return (BACKEND_ROOT / relative).read_text(encoding="utf-8")


def test_normalizes_provider_words_and_segments() -> None:
    result = asr_providers._normalise({"language": "hi", "text": "नमस्ते world", "segments": [{"start": 0, "end": 2, "text": "नमस्ते world", "words": [{"start": 0, "end": .8, "word": "नमस्ते"}, {"start": .8, "end": 2, "word": "world"}]}]}, "groq", "whisper-large-v3", 2, .4, 1)
    assert result.language == "hi" and len(result.words) == 2 and result.timestamp_quality == "provider_word"


@pytest.mark.parametrize(("provider_language", "expected"), [("Hindi", "hi"), ("marathi", "mr"), ("English", "en")])
def test_normalizes_provider_display_language_to_iso(provider_language: str, expected: str) -> None:
    result = asr_providers._normalise(
        {"language": provider_language, "text": "test", "segments": [{"start": 0, "end": 1, "text": "test"}]},
        "groq", "whisper-large-v3", 1, .1, 1,
    )
    assert result.language == expected


def test_normalizes_groq_top_level_words_into_chronological_segments() -> None:
    result = asr_providers._normalise({
        "language": "hi", "text": "one two three", "segments": [
            {"start": 0, "end": 1, "text": "one two"},
            {"start": 1, "end": 2, "text": "three"},
        ],
        "words": [
            {"start": 0, "end": .4, "word": "one"},
            {"start": .4, "end": .9, "word": "two"},
            {"start": 1, "end": 1.5, "word": "three"},
        ],
    }, "groq", "whisper-large-v3", 2, .1, 1)
    assert [word["text"] for word in result.words] == ["one", "two", "three"]
    assert [word["text"] for word in result.segments[0]["words"]] == ["one", "two"]
    assert [word["text"] for word in result.segments[1]["words"]] == ["three"]
    assert result.timestamp_quality == "provider_word"


def test_permanent_groq_error_does_not_call_cloudflare(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = "dummy", "account", "token"
    audio = tmp_path / "sample.flac"; audio.write_bytes(b"fake")
    async def broken(*args, **kwargs): raise asr_providers.ASRProviderError("bad request", status_code=400)
    async def unexpected(*args, **kwargs): raise AssertionError("fallback must not be called")
    monkeypatch.setattr(asr_providers.GroqASRProvider, "transcribe", broken)
    monkeypatch.setattr(asr_providers.CloudflareASRProvider, "transcribe", unexpected)
    with pytest.raises(asr_providers.ASRProviderError): asyncio.run(asr_providers.transcribe_api(audio, language_hint="auto", duration=1))
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = old


def test_retryable_groq_error_uses_cloudflare(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = "dummy", "account", "token"
    audio = tmp_path / "sample.flac"; audio.write_bytes(b"fake")
    async def unavailable(*args, **kwargs): raise asr_providers.ASRProviderError("outage", retryable=True, status_code=503)
    async def fallback(*args, **kwargs): return asr_providers._normalise({"language": "mr", "text": "नमस्कार", "segments": [{"start": 0, "end": 1, "text": "नमस्कार", "words": [{"start": 0, "end": 1, "word": "नमस्कार"}]}]}, "cloudflare", "model", 1, .1, 1)
    monkeypatch.setattr(asr_providers.GroqASRProvider, "transcribe", unavailable)
    monkeypatch.setattr(asr_providers.CloudflareASRProvider, "transcribe", fallback)
    assert asyncio.run(asr_providers.transcribe_api(audio, language_hint="auto", duration=1)).fallback_used
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = old


def test_configured_cloudflare_operates_when_groq_primary_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = "", "account", "token"
    audio = tmp_path / "sample.flac"; audio.write_bytes(b"fake")
    async def unexpected(*args, **kwargs): raise AssertionError("unconfigured Groq must not be called")
    async def cloudflare(*args, **kwargs): return asr_providers._normalise({"language": "hi", "text": "ok", "segments": [{"start": 0, "end": 1, "text": "ok", "words": [{"start": 0, "end": 1, "word": "ok"}]}]}, "cloudflare", "model", 1, .1, 1)
    monkeypatch.setattr(asr_providers.GroqASRProvider, "transcribe", unexpected)
    monkeypatch.setattr(asr_providers.CloudflareASRProvider, "transcribe", cloudflare)
    result = asyncio.run(asr_providers.transcribe_api(audio, language_hint="auto", duration=1))
    assert result.provider == "cloudflare" and result.fallback_used
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = old


def test_api_mode_does_not_eagerly_import_legacy_alignment() -> None:
    source = _source("app/services/transcription.py")
    assert source.count("from .forced_alignment import force_align_whisperx") == 1
    assert source.index("from .forced_alignment import force_align_whisperx") > source.index("if settings.normalized_asr_mode == \"api\":")


def test_worker_records_validated_api_readiness_before_first_heartbeat() -> None:
    worker = _source("app/worker.py")
    assert "provider_capability = await api_asr_runtime_snapshot()" in worker
    assert '"asr": provider_capability' in worker


def test_durable_job_id_is_used_as_provider_correlation_id() -> None:
    routes = _source("app/api/routes.py")
    transcription = _source("app/services/transcription.py")
    assert "request_id=job_id" in routes
    assert "duration=chunk_duration, request_id=request_id" in transcription


def test_api_production_startup_skips_legacy_whisperx_policy() -> None:
    main = _source("app/main.py")
    assert 'if settings.normalized_asr_mode == "local":' in main
    assert main.index('if settings.normalized_asr_mode == "local":') < main.index("validate_production_alignment_policy(")


def test_invalid_asr_mode_fails_closed() -> None:
    settings = get_settings(); original = settings.asr_mode
    settings.asr_mode = "unsupported"
    with pytest.raises(RuntimeError, match="ASR_MODE"):
        _ = settings.normalized_asr_mode
    settings.asr_mode = original


def test_invalid_asr_provider_selection_fails_closed() -> None:
    settings = get_settings(); primary, fallback = settings.asr_primary_provider, settings.asr_fallback_provider
    settings.asr_primary_provider = "typo"
    with pytest.raises(RuntimeError, match="ASR_PRIMARY_PROVIDER"):
        _ = settings.normalized_asr_primary_provider
    settings.asr_primary_provider = primary
    settings.asr_fallback_provider = "other"
    with pytest.raises(RuntimeError, match="ASR_FALLBACK_PROVIDER"):
        _ = settings.normalized_asr_fallback_provider
    settings.asr_fallback_provider = fallback


def test_worker_retry_reuses_current_verified_transcript_before_provider_call() -> None:
    routes = _source("app/api/routes.py")
    reuse = routes.index("Reused existing verified transcript")
    provider_call = routes.index("await transcribe(Path(video[\"file_path\"])")
    assert reuse < provider_call
    assert 'SELECT COUNT(*) count FROM clips WHERE video_id=?' in routes


def test_chunk_results_offset_and_de_duplicate_overlap() -> None:
    def item(text: str, start: float, end: float):
        return asr_providers._normalise({"language": "hi", "text": text, "segments": [{"start": start, "end": end, "text": text, "words": [{"start": start, "end": end, "word": text}]}]}, "groq", "whisper-large-v3", 10, .1, 1)
    merged = asr_providers.merge_chunk_results([(item("first", 0, 9), 0), (item("first", 0, 2), 8), (item("second", 2, 8), 8)])
    assert [row["text"] for row in merged.segments] == ["first", "second"]
    assert merged.segments[-1]["start"] == 10


def test_qualification_runner_stabilizes_before_timestamp_validation() -> None:
    source = _source("scripts/run_api_asr_qualification.py")
    assert source.index("stabilize_word_timestamps(merged.segments)") < source.index("validate_timestamps(merged.segments,duration)")


def test_rate_limit_and_retry_after_are_classified() -> None:
    response = httpx.Response(429, headers={"Retry-After": "3"})
    with pytest.raises(asr_providers.ASRProviderError) as raised:
        asr_providers._raise_for_status(response, "Groq")
    assert raised.value.retryable and raised.value.rate_limited and raised.value.retry_after == 3


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (408, True), (500, True), (503, True)])
def test_provider_status_retry_policy(status: int, retryable: bool) -> None:
    with pytest.raises(asr_providers.ASRProviderError) as raised:
        asr_providers._raise_for_status(httpx.Response(status), "provider")
    assert raised.value.retryable is retryable


def test_malformed_payload_fails_closed() -> None:
    with pytest.raises(asr_providers.ASRProviderError, match="unreadable"):
        asr_providers._normalise({"unexpected": True}, "groq", "whisper-large-v3", 1, .1, 1)


def test_provider_readiness_requires_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings(); old = settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token
    settings.groq_api_keys = settings.cloudflare_account_id = settings.cloudflare_api_token = ""
    ready = asyncio.run(asr_providers.probe_api_asr_readiness())
    assert ready["api_asr_ready"] is False and ready["primary_status"] == "unconfigured"
    settings.groq_api_keys, settings.cloudflare_account_id, settings.cloudflare_api_token = old


def test_groq_rotates_key_only_after_rate_limit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.groq_api_keys, settings.asr_provider_max_attempts
    settings.groq_api_keys, settings.asr_provider_max_attempts = "key-one,key-two", 1
    audio = tmp_path / "tiny.flac"; audio.write_bytes(b"audio")
    calls: list[str] = []
    responses = [httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200, json={"language": "hi", "text": "test", "segments": [{"start": 0, "end": 1, "text": "test", "words": [{"start": 0, "end": 1, "word": "test"}]}]})]
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            calls.append(kwargs["headers"]["Authorization"])
            return responses.pop(0)
    monkeypatch.setattr(asr_providers.httpx, "AsyncClient", Client)
    result = asyncio.run(asr_providers.GroqASRProvider().transcribe(audio, language_hint="auto", duration=1))
    assert result.provider == "groq" and result.request_attempts == 2 and calls == ["Bearer key-one", "Bearer key-two"]
    settings.groq_api_keys, settings.asr_provider_max_attempts = old


def test_cloudflare_normalizes_wrapped_success(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.cloudflare_account_id, settings.cloudflare_api_token
    settings.cloudflare_account_id, settings.cloudflare_api_token = "account", "token"
    audio = tmp_path / "tiny.flac"; audio.write_bytes(b"audio")
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(200, json={"result": {"language": "mr", "text": "test", "segments": [{"start": 0, "end": 1, "text": "test", "words": [{"start": 0, "end": 1, "word": "test"}]}]}})
    monkeypatch.setattr(asr_providers.httpx, "AsyncClient", Client)
    result = asyncio.run(asr_providers.CloudflareASRProvider().transcribe(audio, language_hint="mr", duration=1))
    assert result.provider == "cloudflare" and result.language == "mr" and calls[0]["json"]["language"] == "mr"
    settings.cloudflare_account_id, settings.cloudflare_api_token = old


@pytest.mark.parametrize("language_hint,expected", [("hi", "hi"), ("mr", "mr"), ("hinglish", None), ("auto", None)])
def test_groq_language_routing_preserves_hinglish_auto_detection(monkeypatch: pytest.MonkeyPatch, tmp_path, language_hint: str, expected: str | None) -> None:
    settings = get_settings(); old = settings.groq_api_keys
    settings.groq_api_keys = "dummy-key"
    audio = tmp_path / "tiny.flac"; audio.write_bytes(b"audio")
    observed = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            observed.append(kwargs["data"])
            return httpx.Response(200, json={"language": "hi", "text": "test", "segments": [{"start": 0, "end": 1, "text": "test", "words": [{"start": 0, "end": 1, "word": "test"}]}]})
    monkeypatch.setattr(asr_providers.httpx, "AsyncClient", Client)
    asyncio.run(asr_providers.GroqASRProvider().transcribe(audio, language_hint=language_hint, duration=1))
    assert observed[0].get("language") == expected
    settings.groq_api_keys = old


def test_cloudflare_timeout_and_malformed_response_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.cloudflare_account_id, settings.cloudflare_api_token
    settings.cloudflare_account_id, settings.cloudflare_api_token = "account", "token"
    audio = tmp_path / "tiny.flac"; audio.write_bytes(b"audio")
    class TimeoutClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(asr_providers.httpx, "AsyncClient", TimeoutClient)
    with pytest.raises(asr_providers.ASRProviderError, match="timed out"):
        asyncio.run(asr_providers.CloudflareASRProvider().transcribe(audio, language_hint="auto", duration=1))
    class MalformedClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return httpx.Response(200, json={"result": {"unexpected": True}})
    monkeypatch.setattr(asr_providers.httpx, "AsyncClient", MalformedClient)
    with pytest.raises(asr_providers.ASRProviderError, match="unreadable"):
        asyncio.run(asr_providers.CloudflareASRProvider().transcribe(audio, language_hint="auto", duration=1))
    settings.cloudflare_account_id, settings.cloudflare_api_token = old


def test_cloudflare_retries_temporary_5xx(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings = get_settings(); old = settings.cloudflare_account_id, settings.cloudflare_api_token, settings.asr_provider_max_attempts
    settings.cloudflare_account_id, settings.cloudflare_api_token, settings.asr_provider_max_attempts = "account", "token", 2
    audio = tmp_path / "tiny.flac"; audio.write_bytes(b"audio")
    responses = [httpx.Response(503), httpx.Response(200, json={"result": {"language": "hi", "text": "ok", "segments": [{"start": 0, "end": 1, "text": "ok", "words": [{"start": 0, "end": 1, "word": "ok"}]}]}})]
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return responses.pop(0)
    async def no_sleep(*args, **kwargs): return None
    monkeypatch.setattr(asr_providers.httpx, "AsyncClient", Client)
    monkeypatch.setattr(asr_providers.asyncio, "sleep", no_sleep)
    result = asyncio.run(asr_providers.CloudflareASRProvider().transcribe(audio, language_hint="auto", duration=1))
    assert result.request_attempts == 2
    settings.cloudflare_account_id, settings.cloudflare_api_token, settings.asr_provider_max_attempts = old


def test_api_mode_does_not_apply_legacy_consensus_or_whisperx_gate() -> None:
    settings = get_settings()
    old_mode, old_consensus, old_alignment = settings.asr_mode, settings.require_asr_consensus, settings.require_forced_alignment
    settings.asr_mode, settings.require_asr_consensus, settings.require_forced_alignment = "api", True, True
    assert settings.effective_require_asr_consensus is False
    assert settings.effective_require_forced_alignment is False
    settings.asr_mode = "local"
    assert settings.effective_require_asr_consensus is True
    assert settings.effective_require_forced_alignment is True
    settings.asr_mode, settings.require_asr_consensus, settings.require_forced_alignment = old_mode, old_consensus, old_alignment

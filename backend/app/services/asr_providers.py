"""Server-side API ASR providers. No provider secret is returned or logged."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("clipkaro.asr")
_LAST_SUCCESSFUL_PROVIDER: str | None = None
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


class ASRProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, rate_limited: bool = False, status_code: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.retryable, self.rate_limited, self.status_code, self.retry_after = retryable, rate_limited, status_code, retry_after


# Canonical fallback reason categories for durable observability.
FALLBACK_REASON_CATEGORIES = frozenset({
    "TIMEOUT",
    "RATE_LIMIT",
    "QUOTA",
    "AUTH_CONFIG",
    "NETWORK",
    "PROVIDER_5XX",
    "PROVIDER_4XX",
    "INVALID_RESPONSE",
    "EMPTY_RESULT",
    "TIMESTAMP_INVALID",
    "MALFORMED_RESPONSE",
    "UNKNOWN_PROVIDER_ERROR",
})


def _normalize_fallback_reason(category: str) -> str:
    """Normalize a fallback reason to a canonical category."""
    normalized = category.upper()
    return normalized if normalized in FALLBACK_REASON_CATEGORIES else "UNKNOWN_PROVIDER_ERROR"


@dataclass
class ASRResult:
    provider: str
    model: str
    language: str
    language_confidence: float | None
    text: str
    segments: list[dict[str, Any]]
    words: list[dict[str, Any]]
    duration: float
    provider_latency: float
    request_attempts: int
    fallback_used: bool = False
    timestamp_quality: str = "provider_native"
    metadata: dict[str, Any] = field(default_factory=dict)
    # Observability fields (populated by provider chain, persisted to transcript)
    primary_provider: str | None = None
    final_provider: str | None = None
    provider_attempt_count: int = 0
    retry_count: int = 0
    fallback_provider: str | None = None
    fallback_reason_category: str | None = None
    asr_success: bool = True
    attempts_trace: list[dict[str, Any]] = field(default_factory=list)


def _retry_after(response: httpx.Response) -> float | None:
    try: return max(0.0, float(response.headers.get("retry-after", "")))
    except ValueError: return None


def _raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.is_success: return
    status, retry_after = response.status_code, _retry_after(response)
    if status == 429: raise ASRProviderError(f"{provider} rate limit", retryable=True, rate_limited=True, status_code=status, retry_after=retry_after)
    if status in {408, 409, 425} or status >= 500: raise ASRProviderError(f"{provider} temporary failure", retryable=True, status_code=status, retry_after=retry_after)
    raise ASRProviderError(f"{provider} rejected the transcription request", status_code=status)


def _float(value: Any, default: float = 0.0) -> float:
    try: return round(float(value), 3)
    except (TypeError, ValueError): return default


def _normalise(payload: dict[str, Any], provider: str, model: str, duration: float, latency: float, attempts: int) -> ASRResult:
    raw_segments = payload.get("segments") or payload.get("transcription_info", {}).get("segments") or []
    segments, words = [], []
    for raw in raw_segments:
        if not isinstance(raw, dict): continue
        text = str(raw.get("text") or raw.get("word") or "").strip()
        start, end = _float(raw.get("start")), _float(raw.get("end"))
        raw_words = raw.get("words") or []
        current_words = []
        for word in raw_words:
            if not isinstance(word, dict): continue
            item = {"start": _float(word.get("start")), "end": _float(word.get("end")), "text": str(word.get("word") or word.get("text") or "").strip()}
            if item["text"] and item["end"] > item["start"]:
                if word.get("confidence") is not None: item["confidence"] = _float(word.get("confidence"))
                current_words.append(item); words.append(item)
        if text and end > start:
            row = {"start": start, "end": end, "text": text, "words": current_words}
            for key in ("avg_logprob", "no_speech_prob", "compression_ratio"):
                if raw.get(key) is not None: row[key] = _float(raw[key])
            segments.append(row)
    # Groq verbose_json returns words at the response top level while several
    # OpenAI-compatible providers nest them inside each segment.  Normalise both
    # shapes; never discard valid provider-native word timings merely because the
    # enclosing segment schema differs.
    raw_top_level_words = payload.get("words") or payload.get("transcription_info", {}).get("words") or []
    if not words and isinstance(raw_top_level_words, list):
        for word in raw_top_level_words:
            if not isinstance(word, dict):
                continue
            item = {"start": _float(word.get("start")), "end": _float(word.get("end")), "text": str(word.get("word") or word.get("text") or "").strip()}
            if item["text"] and item["end"] > item["start"]:
                if word.get("confidence") is not None:
                    item["confidence"] = _float(word.get("confidence"))
                words.append(item)
        # Assign every word once to the segment containing its start. A word
        # straddling a provider segment boundary belongs to the later segment
        # only when it begins there, preserving chronological caption order.
        for word in words:
            for index, segment in enumerate(segments):
                if segment["start"] <= word["start"] < segment["end"] or (
                    index == len(segments) - 1 and word["start"] == segment["end"]
                ):
                    segment["words"].append(word)
                    break
    text = str(payload.get("text") or payload.get("transcription_info", {}).get("text") or "").strip()
    if not text and segments: text = " ".join(row["text"] for row in segments)
    if not text: raise ASRProviderError(f"{provider} returned an unreadable transcription payload")
    language = str(payload.get("language") or payload.get("transcription_info", {}).get("language") or "auto").strip().lower()
    # Providers commonly return display names in verbose JSON while ClipKaro's
    # language gate uses ISO-639-1.  Normalise names at the provider boundary;
    # otherwise a correctly detected "hindi"/"marathi" is incorrectly scored
    # as a language mismatch and leaks an invalid value downstream.
    language = {"hindi": "hi", "marathi": "mr", "english": "en", "urdu": "ur"}.get(language, language)
    confidence = payload.get("language_probability") or payload.get("language_confidence")
    return ASRResult(
        provider=provider,
        model=model,
        language=language,
        language_confidence=_float(confidence) if confidence is not None else None,
        text=text,
        segments=segments,
        words=words,
        duration=duration,
        provider_latency=round(latency, 3),
        request_attempts=attempts,
        timestamp_quality="provider_word" if words else "provider_segment" if segments else "unavailable",
        primary_provider=provider,
        final_provider=provider,
        provider_attempt_count=attempts,
        retry_count=0,
        fallback_used=False,
        fallback_provider=None,
        fallback_reason_category=None,
        asr_success=True,
        attempts_trace=[],
    )


class ASRProvider:
    name = "provider"
    async def transcribe(self, audio: Path, *, language_hint: str, duration: float, request_id: str = "") -> ASRResult: raise NotImplementedError


class GroqASRProvider(ASRProvider):
    name = "groq"
    async def transcribe(self, audio: Path, *, language_hint: str, duration: float, request_id: str = "") -> ASRResult:
        settings, keys = get_settings(), get_settings().groq_keys
        if not keys: raise ASRProviderError("Groq ASR credential is not configured")
        model, max_attempts = settings.groq_asr_model, max(1, settings.asr_provider_max_attempts)
        last: ASRProviderError | None = None
        total_attempts = 0
        for key_index, key in enumerate(keys):
            for attempt in range(1, max_attempts + 1):
                total_attempts += 1
                started = time.perf_counter()
                try:
                    data = {"model": model, "response_format": "verbose_json", "timestamp_granularities[]": ["word", "segment"], "temperature": "0"}
                    if language_hint not in {"", "auto", "hinglish"}: data["language"] = language_hint
                    headers = {"Authorization": f"Bearer {key}"}
                    if request_id: headers["X-Request-ID"] = request_id
                    with audio.open("rb") as handle:
                        async with httpx.AsyncClient(timeout=settings.asr_provider_timeout_seconds) as client:
                            response = await client.post(GROQ_URL, headers=headers, data=data, files={"file": (audio.name, handle, "audio/flac")})
                    _raise_for_status(response, "Groq")
                    return _normalise(response.json(), self.name, model, duration, time.perf_counter()-started, total_attempts)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last = ASRProviderError("Groq request timed out", retryable=True)
                except ASRProviderError as exc:
                    last = exc
                    if not exc.retryable: raise
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ASRProviderError("Groq returned malformed JSON") from exc
                if attempt < max_attempts:
                    await asyncio.sleep(last.retry_after if last and last.retry_after is not None else min(8.0, .4 * 2 ** (attempt - 1)) + random.uniform(0, .15))
            if not (last and last.rate_limited): break
            logger.warning("asr_provider_rate_limit provider=groq key_slot=%s", key_index + 1)
        raise last or ASRProviderError("Groq ASR failed")


class CloudflareASRProvider(ASRProvider):
    name = "cloudflare"
    async def transcribe(self, audio: Path, *, language_hint: str, duration: float, request_id: str = "") -> ASRResult:
        settings = get_settings()
        if not settings.cloudflare_account_id or not settings.cloudflare_api_token: raise ASRProviderError("Cloudflare ASR is not configured")
        body: dict[str, Any] = {"audio": base64.b64encode(audio.read_bytes()).decode("ascii"), "task": "transcribe", "vad_filter": True, "condition_on_previous_text": False, "compression_ratio_threshold": 2.4, "no_speech_threshold": .6, "log_prob_threshold": -1.0}
        if language_hint not in {"", "auto", "hinglish"}: body["language"] = language_hint
        headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}
        if request_id: headers["X-Request-ID"] = request_id
        last: ASRProviderError | None = None
        for attempt in range(1, max(1, settings.asr_provider_max_attempts) + 1):
            started = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=settings.asr_provider_timeout_seconds) as client:
                    response = await client.post(CLOUDFLARE_URL.format(account=settings.cloudflare_account_id, model=settings.cloudflare_asr_model), headers=headers, json=body)
                _raise_for_status(response, "Cloudflare")
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("result"), dict): payload = payload["result"]
                return _normalise(payload, self.name, settings.cloudflare_asr_model, duration, time.perf_counter()-started, attempt)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last = ASRProviderError("Cloudflare request timed out", retryable=True)
            except ASRProviderError as exc:
                last = exc
                if not exc.retryable: raise
            except (json.JSONDecodeError, ValueError) as exc: raise ASRProviderError("Cloudflare returned malformed JSON") from exc
            if attempt < max(1, settings.asr_provider_max_attempts):
                await asyncio.sleep(last.retry_after if last and last.retry_after is not None else min(8.0, .4 * 2 ** (attempt - 1)) + random.uniform(0, .15))
        raise last or ASRProviderError("Cloudflare ASR failed")


async def probe_api_asr_readiness() -> dict[str, Any]:
    s = get_settings(); groq = bool(s.groq_keys); cloudflare = bool(s.cloudflare_account_id and s.cloudflare_api_token)
    primary_provider, fallback_provider = s.normalized_asr_primary_provider, s.normalized_asr_fallback_provider
    primary = groq if primary_provider == "groq" else cloudflare
    fallback = cloudflare if fallback_provider == "cloudflare" else False
    return {"mode": s.normalized_asr_mode, "primary_provider": primary_provider, "primary_status": "configured" if primary else "unconfigured", "fallback_provider": fallback_provider or "none", "fallback_status": "configured" if fallback else "unconfigured", "api_asr_ready": bool(primary or fallback)}


async def api_asr_runtime_snapshot() -> dict[str, Any]:
    """Secret-free worker heartbeat payload; configuration is not a paid probe."""
    payload = await probe_api_asr_readiness()
    payload["last_successful_provider"] = _LAST_SUCCESSFUL_PROVIDER
    return payload


async def _transcribe_legacy_api(audio: Path, *, language_hint: str, duration: float, request_id: str = "") -> ASRResult:
    s = get_settings()
    readiness = await probe_api_asr_readiness()
    primary_name = s.normalized_asr_primary_provider
    # A configured Cloudflare fallback is an operational degraded mode when the
    # desired Groq primary has no usable credential. Do not call Groq first.
    degraded_to_fallback = bool(readiness["api_asr_ready"]) and readiness["primary_status"] != "configured" and readiness["fallback_status"] == "configured"
    primary = CloudflareASRProvider() if degraded_to_fallback or primary_name == "cloudflare" else GroqASRProvider()
    global _LAST_SUCCESSFUL_PROVIDER
    # Track the intended primary provider for observability
    intended_primary = primary.name
    primary_started = time.perf_counter()
    primary_latency = 0.0
    primary_error: ASRProviderError | None = None
    try:
        result = await primary.transcribe(audio, language_hint=language_hint, duration=duration, request_id=request_id)
        primary_latency = time.perf_counter() - primary_started
        result.fallback_used = degraded_to_fallback
        result.primary_provider = intended_primary
        result.final_provider = result.provider
        result.provider_attempt_count = result.request_attempts
        result.retry_count = max(0, result.request_attempts - 1)  # retries = attempts - 1 for same provider
        result.fallback_provider = "cloudflare" if degraded_to_fallback else None
        result.fallback_reason_category = None if not degraded_to_fallback else "DEGRADED_PRIMARY"
        result.asr_success = True
        result.attempts_trace = [{
            "provider": result.provider,
            "attempt": 1,
            "success": True,
            "latency_ms": round(primary_latency * 1000),
            "failure_category": None,
        }]
        _LAST_SUCCESSFUL_PROVIDER = result.provider
        return result
    except ASRProviderError as error:
        primary_latency = time.perf_counter() - primary_started
        primary_error = error
        if not error.retryable or s.normalized_asr_fallback_provider != "cloudflare" or primary.name == "cloudflare":
            # No fallback possible or not retryable - return failed result with observability
            failed_result = ASRResult(
                provider=primary.name,
                model=getattr(primary, 'model', 'unknown'),
                language="unknown",
                language_confidence=None,
                text="",
                segments=[],
                words=[],
                duration=duration,
                provider_latency=round(primary_latency, 3),
                request_attempts=1,
                fallback_used=False,
                primary_provider=intended_primary,
                final_provider=None,
                provider_attempt_count=1,
                retry_count=0,
                fallback_provider=None,
                fallback_reason_category=_normalize_fallback_reason(_failure_class(error)),
                asr_success=False,
                attempts_trace=[{
                    "provider": primary.name,
                    "attempt": 1,
                    "success": False,
                    "latency_ms": round(primary_latency * 1000),
                    "failure_category": _normalize_fallback_reason(_failure_class(error)),
                }],
            )
            _LAST_SUCCESSFUL_PROVIDER = None
            raise error
        fallback = await CloudflareASRProvider().transcribe(audio, language_hint=language_hint, duration=duration, request_id=request_id)
        fallback.fallback_used = True
        fallback.primary_provider = intended_primary
        fallback.final_provider = fallback.provider
        fallback.provider_attempt_count = 1 + fallback.request_attempts
        fallback.retry_count = fallback.request_attempts - 1 if fallback.request_attempts > 1 else 0
        fallback.fallback_provider = "cloudflare"
        fallback.fallback_reason_category = _normalize_fallback_reason(_failure_class(error))
        fallback.asr_success = True
        fallback.attempts_trace = [
            {
                "provider": intended_primary,
                "attempt": 1,
                "success": False,
                "latency_ms": round(primary_latency * 1000),
                "failure_category": _normalize_fallback_reason(_failure_class(error)),
            },
            {
                "provider": fallback.provider,
                "attempt": 1,
                "success": True,
                "latency_ms": round(fallback.provider_latency * 1000),
                "failure_category": None,
            },
        ]
        _LAST_SUCCESSFUL_PROVIDER = fallback.provider
        logger.warning("asr_fallback provider=cloudflare source=groq status_class=%s", f"{error.status_code // 100 if error.status_code else 0}xx")
        return fallback


def _hinglish_request(language_hint: str) -> bool:
    return language_hint.strip().lower().replace("-", "_") in {"hinglish", "roman_hinglish"}


def _failure_class(error: ASRProviderError) -> str:
    if error.rate_limited:
        return "rate_limit"
    if error.status_code and error.status_code >= 500:
        return "provider_5xx"
    if error.status_code and error.status_code >= 400:
        return "provider_4xx"
    message = str(error).casefold()
    if "timeout" in message or "timed out" in message:
        return "timeout"
    if "malformed" in message or "unreadable" in message or "empty" in message:
        return "invalid_response"
    return "connectivity" if error.retryable else "internal_processing_error"


async def _transcribe_elevenlabs_hinglish(audio: Path, *, language_hint: str, duration: float, request_id: str = "") -> ASRResult:
    """Candidate path: bounded ElevenLabs attempt, then the existing API route.

    This deliberately never scores text or makes a quality-based fallback.
    Authentication/configuration failures stay fail-closed; transient provider
    failures and unusable/malformed responses may use the legacy route.
    """
    s = get_settings()
    keys = s.elevenlabs_keys
    if not keys:
        raise ASRProviderError("ElevenLabs Hinglish ASR credential is not configured")
    from .candidate_asr_providers import ElevenLabsScribeV2Provider
    last: ASRProviderError | None = None
    key_index = 0
    elevenlabs_started = time.perf_counter()
    elevenlabs_latency = 0.0
    elevenlabs_attempts = 0
    elevenlabs_trace: list[dict[str, Any]] = []
    for attempt in range(1, max(1, s.asr_provider_max_attempts) + 1):
        elevenlabs_attempts += 1
        attempt_started = time.perf_counter()
        try:
            provider_timeout = max(s.asr_provider_timeout_seconds, s.elevenlabs_asr_timeout_seconds)
            result = await ElevenLabsScribeV2Provider(keys[key_index], provider_timeout).transcribe(
                audio, language_hint="hinglish", duration=duration, request_id=request_id
            )
            if not result.text.strip() or not result.words:
                raise ASRProviderError("ElevenLabs returned an empty or unusable transcript")
            attempt_latency = time.perf_counter() - attempt_started
            elevenlabs_latency = time.perf_counter() - elevenlabs_started
            result.request_attempts = attempt
            # Populate observability for successful ElevenLabs path
            result.primary_provider = "elevenlabs"
            result.final_provider = "elevenlabs"
            result.provider_attempt_count = result.request_attempts
            result.retry_count = max(0, result.request_attempts - 1)
            result.fallback_used = False
            result.fallback_provider = None
            result.fallback_reason_category = None
            result.asr_success = True
            elevenlabs_trace.append({
                "provider": "elevenlabs",
                "attempt": attempt,
                "success": True,
                "latency_ms": round(attempt_latency * 1000),
                "failure_category": None,
            })
            result.attempts_trace = elevenlabs_trace
            return result
        except ASRProviderError as error:
            attempt_latency = time.perf_counter() - attempt_started
            last = error
            elevenlabs_trace.append({
                "provider": "elevenlabs",
                "attempt": attempt,
                "success": False,
                "latency_ms": round(attempt_latency * 1000),
                "failure_category": _normalize_fallback_reason(_failure_class(error)),
            })
            # Explicit configuration/auth errors are not a reason to conceal a
            # deployment issue by charging another provider.
            if not error.retryable and _failure_class(error) not in {"invalid_response"}:
                # Failed permanently - create failed result with observability
                failed_result = ASRResult(
                    provider="elevenlabs",
                    model="scribe_v2",
                    language="unknown",
                    language_confidence=None,
                    text="",
                    segments=[],
                    words=[],
                    duration=duration,
                    provider_latency=round(time.perf_counter() - elevenlabs_started, 3),
                    request_attempts=elevenlabs_attempts,
                    fallback_used=False,
                    primary_provider="elevenlabs",
                    final_provider=None,
                    provider_attempt_count=elevenlabs_attempts,
                    retry_count=max(0, elevenlabs_attempts - 1),
                    fallback_provider=None,
                    fallback_reason_category=_normalize_fallback_reason(_failure_class(error)),
                    asr_success=False,
                    attempts_trace=elevenlabs_trace,
                )
                raise error
            # A different key can help only when the provider explicitly says
            # this key is quota/rate-limited.  Never rotate for 4xx requests,
            # malformed payloads, network failures, or application bugs.
            if error.rate_limited and len(keys) > 1:
                key_index = (key_index + 1) % len(keys)
            if attempt < max(1, s.asr_provider_max_attempts):
                await asyncio.sleep(error.retry_after if error.retry_after is not None else min(8.0, .4 * 2 ** (attempt - 1)) + random.uniform(0, .15))
    assert last is not None
    elevenlabs_latency = time.perf_counter() - elevenlabs_started
    try:
        fallback = await _transcribe_legacy_api(audio, language_hint="hinglish", duration=duration, request_id=request_id)
        fallback.fallback_used = True
        fallback.primary_provider = "elevenlabs"
        fallback.final_provider = fallback.provider
        fallback.provider_attempt_count = elevenlabs_attempts + fallback.request_attempts
        fallback.retry_count = max(0, fallback.request_attempts - 1)
        fallback.fallback_provider = fallback.provider
        fallback.fallback_reason_category = _normalize_fallback_reason(_failure_class(last))
        # Backward compatibility: keep fallback_reason in metadata for existing tests/consumers
        # Use original lowercase category from _failure_class for backward compatibility
        fallback.metadata.update({
            "fallback_reason": _failure_class(last),
            "primary_provider": "elevenlabs",
        })
        fallback.asr_success = True
        # Combine ElevenLabs trace with fallback trace
        fallback_trace = []
        for trace in elevenlabs_trace:
            fallback_trace.append(trace)
        # Add the fallback provider's trace
        if fallback.attempts_trace:
            fallback_trace.extend(fallback.attempts_trace)
        else:
            fallback_trace.append({
                "provider": fallback.provider,
                "attempt": 1,
                "success": True,
                "latency_ms": round(fallback.provider_latency * 1000),
                "failure_category": None,
            })
        fallback.attempts_trace = fallback_trace
        logger.warning("hinglish_asr_fallback provider=%s source=elevenlabs", fallback.provider)
        return fallback
    except ASRProviderError as fallback_error:
        # All providers failed - raise with combined observability
        raise ASRProviderError("All configured Hinglish ASR providers failed", retryable=fallback_error.retryable) from fallback_error


async def transcribe_api(audio: Path, *, language_hint: str, duration: float, request_id: str = "", asr_route: str = "legacy") -> ASRResult:
    """Use the durable job route; never consult a mutable rollout allowlist."""
    if _hinglish_request(language_hint) and asr_route == "elevenlabs_roman":
        return await _transcribe_elevenlabs_hinglish(audio, language_hint=language_hint, duration=duration, request_id=request_id)
    return await _transcribe_legacy_api(audio, language_hint=language_hint, duration=duration, request_id=request_id)


def merge_chunk_results(chunks: list[tuple[ASRResult, float]]) -> ASRResult:
    """Offset timestamps and discard overlap duplicates deterministically."""
    if not chunks: raise ASRProviderError("No API transcription chunks were returned")
    merged, last_end = [], 0.0
    total_latency = 0.0
    total_attempts = 0
    any_fallback = False
    combined_trace: list[dict[str, Any]] = []
    primary_provider = None
    final_provider = None
    fallback_provider = None
    fallback_reason_category = None
    asr_success = True
    
    for result, offset in chunks:
        # Track primary provider from first chunk
        if primary_provider is None:
            primary_provider = result.primary_provider
        # Track final provider from last successful chunk
        if result.asr_success:
            final_provider = result.final_provider
        # Aggregate latency and attempts
        total_latency += result.provider_latency
        total_attempts += result.request_attempts
        any_fallback = any_fallback or result.fallback_used
        if result.fallback_provider:
            fallback_provider = result.fallback_provider
        if result.fallback_reason_category:
            fallback_reason_category = result.fallback_reason_category
        if not result.asr_success:
            asr_success = False
        # Combine attempts trace
        combined_trace.extend(result.attempts_trace)
        
        for segment in result.segments:
            row = {**segment, "start": round(float(segment["start"]) + offset, 3), "end": round(float(segment["end"]) + offset, 3)}
            if row["end"] <= last_end + .02: continue
            if row["start"] <= last_end + .02 and merged and str(row["text"]).strip().casefold() == str(merged[-1]["text"]).strip().casefold(): continue
            words = []
            for word in segment.get("words") or []:
                item = {**word, "start": round(float(word["start"]) + offset, 3), "end": round(float(word["end"]) + offset, 3)}
                if item["end"] > last_end + .02: words.append(item)
            if words:
                row["words"], row["start"], row["end"] = words, words[0]["start"], words[-1]["end"]
            merged.append(row); last_end = max(last_end, row["end"])
    
    first = chunks[0][0]
    return ASRResult(
        provider=first.provider,
        model=first.model,
        language=first.language,
        language_confidence=first.language_confidence,
        text=" ".join(str(row["text"]) for row in merged),
        segments=merged,
        words=[word for row in merged for word in row.get("words") or []],
        duration=max(row["end"] for row in merged),
        provider_latency=round(total_latency, 3),
        request_attempts=total_attempts,
        fallback_used=any_fallback,
        timestamp_quality=first.timestamp_quality,
        primary_provider=primary_provider,
        final_provider=final_provider,
        provider_attempt_count=total_attempts,
        retry_count=0,  # Retry count is per-provider, not meaningful across chunks
        fallback_provider=fallback_provider,
        fallback_reason_category=fallback_reason_category,
        asr_success=asr_success,
        attempts_trace=combined_trace,
    )

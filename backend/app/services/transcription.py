import asyncio
import json
import gc
import shutil
from pathlib import Path
from typing import Any
from .video import extract_audio, extract_api_audio, probe_audio_duration, chunk_api_audio
from app.core.config import get_settings
from .asr_gate import asr_slot
from .asr_quality import assess_transcript
from .transcript_verification import attach_provenance, transcript_agreement, verify_segments
from .roman_hindi import add_roman_display_text
from .timestamp_stabilization import stabilize_word_timestamps
from .speech_activity import SPEECH_ACTIVITY_VERSION, detect_speech_regions
from .asr_providers import ASRProviderError, transcribe_api, merge_chunk_results
from .hinglish_roman_pipeline import apply_roman_v3_display_v1


def needs_hindi_retry(detected: str, probability: float, language_hint: str, bias: str) -> bool:
    """Disambiguate acoustically similar Hindi/Urdu and uncertain English for an India-first product."""
    if language_hint not in {"", "auto"} or bias != "india":
        return False
    return detected == "ur" or (detected == "en" and probability < .72)


async def transcribe(video_path: Path, model_name: str = "small", language_hint: str = "auto", request_id: str = "", asr_route: str = "legacy", *, generated_dialogue: bool = False) -> tuple[str, list[dict[str, Any]]]:
    """Run one source through ClipKaro's globally bounded ASR pipeline.

    The gate wraps audio extraction, model loading, primary decoding, recovery
    decoding, consensus decoding and optional forced alignment. That means a
    second upload cannot allocate another Whisper model while the first source
    is still consuming the host's RAM/CPU budget.
    """
    async with asr_slot(video_path):
        return await _transcribe_impl(video_path, model_name, language_hint, request_id, asr_route, generated_dialogue=generated_dialogue)


async def _transcribe_impl(video_path: Path, model_name: str = "small", language_hint: str = "auto", request_id: str = "", asr_route: str = "legacy", *, generated_dialogue: bool = False) -> tuple[str, list[dict[str, Any]]]:
    """Transcribe locally with faster-whisper using CPU-safe int8 inference."""
    settings = get_settings()
    if settings.transcription_backend == "fixture":
        if settings.app_env != "test":
            raise RuntimeError("Fixture transcription is restricted to APP_ENV=test.")
        path = settings.transcription_fixture_path
        if not path.exists(): raise RuntimeError(f"E2E transcript fixture was not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        segments = payload.get("segments", [])
        if segments and not any(segment.get("speech_regions") for segment in segments):
            fixture_regions = [
                {"start": round(float(segment.get("start", 0)), 3), "end": round(float(segment.get("end", 0)), 3)}
                for segment in segments
                if float(segment.get("end", 0)) > float(segment.get("start", 0))
            ]
            if fixture_regions:
                segments[0]["speech_activity_version"] = SPEECH_ACTIVITY_VERSION
                segments[0]["speech_regions"] = fixture_regions
        return payload.get("language", "en"), segments
    if settings.normalized_asr_mode == "api":
        return await _transcribe_api_impl(video_path, language_hint, request_id, asr_route, generated_dialogue=generated_dialogue)
    min_clean_seconds = 0.1 if generated_dialogue else 20.0
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed correctly. Activate backend/.venv and run: python -m pip install -r requirements.txt"
        ) from exc
    audio_path = video_path.with_suffix(".wav")
    await extract_audio(video_path, audio_path)
    speech_regions = await asyncio.to_thread(detect_speech_regions, audio_path)

    def run() -> tuple[str, list[dict[str, Any]]]:
        settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(model_name, device="cpu", compute_type="int8",
                             cpu_threads=max(1, settings.asr_cpu_threads),
                             num_workers=max(1, settings.asr_workers),
                             download_root=str(settings.model_cache_dir))
        requested_language = None if language_hint in {"", "auto"} else ("hi" if language_hint == "hinglish" else language_hint)

        def language_context(language: str | None) -> dict[str, str]:
            if language != "hi": return {}
            return {
                "initial_prompt": (
                    "यह स्वाभाविक हिंदी और Hinglish बातचीत है। अंग्रेज़ी शब्दों को सही English spelling में "
                    "लिखें। केवल साफ़ सुनाई देने वाले शब्द लिखें; अनुमान या दोहराव न करें।"
                ),
                "hotwords": "engineering college interview comedy business technology AI software creator video",
            }

        def decode(language: str | None, recovery: bool = False) -> tuple[Any, list[dict[str, Any]], float]:
            segments, info = model.transcribe(
                str(audio_path), language=language, task="transcribe",
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 350, "speech_pad_ms": 180},
                beam_size=5 if recovery else 3, best_of=3, patience=1.15 if recovery else 1.0, temperature=0,
                repetition_penalty=1.15 if recovery else 1.0,
                no_repeat_ngram_size=3 if recovery else 0,
                compression_ratio_threshold=2.2, log_prob_threshold=-1.0, no_speech_threshold=.6,
                word_timestamps=True, condition_on_previous_text=False,
                **language_context(language),
            )
            rows, logprobs = [], []
            for segment in segments:
                words = [
                    {"start": round(word.start, 3), "end": round(word.end, 3), "text": word.word.strip(),
                     "confidence": round(float(word.probability), 3)}
                    for word in (segment.words or []) if word.word.strip()
                ]
                rows.append({"start": round(segment.start, 3), "end": round(segment.end, 3),
                             "text": segment.text.strip(), "words": words,
                             "avg_logprob": round(float(getattr(segment, "avg_logprob", -10)), 3),
                             "no_speech_prob": round(float(getattr(segment, "no_speech_prob", 0)), 3),
                             "compression_ratio": round(float(getattr(segment, "compression_ratio", 0)), 3)})
                logprobs.append(float(getattr(segment, "avg_logprob", -10)))
            quality = sum(logprobs) / len(logprobs) if logprobs else -10
            return info, rows, quality

        info, rows, quality = decode(requested_language)
        final_language = info.language
        probability = float(getattr(info, "language_probability", 1))
        if needs_hindi_retry(info.language, probability, language_hint, settings.auto_language_bias):
            hindi_info, hindi_rows, hindi_quality = decode("hi")
            # Urdu and Hindi are acoustically ambiguous to Whisper. Prefer Devanagari for this
            # India-first UI; for uncertain English, accept Hindi unless its ASR score is much worse.
            if info.language == "ur" or hindi_quality >= quality - .15:
                info, rows = hindi_info, hindi_rows
                final_language = "hi"
        assessment = assess_transcript(rows, final_language, min_clean_seconds=min_clean_seconds)
        if not assessment["accepted"]:
            retry_info, retry_rows, _ = decode("hi" if final_language in {"hi", "ur"} else requested_language, True)
            retry_language = "hi" if final_language in {"hi", "ur"} else retry_info.language
            retry_assessment = assess_transcript(retry_rows, retry_language, min_clean_seconds=min_clean_seconds)
            if retry_assessment["clean_duration"] > assessment["clean_duration"]:
                final_language, assessment = retry_language, retry_assessment
        if not assessment["accepted"]:
            flags = ", ".join(assessment["flags"]) or "insufficient reliable speech"
            raise RuntimeError(f"Transcript quality verification failed ({flags}). No clips were created. Try clearer audio or choose the correct language.")
        verified = assessment["segments"]
        agreement_score = None
        secondary_name = settings.whisper_secondary_model.strip()
        if settings.require_asr_consensus and secondary_name and secondary_name != model_name:
            del decode
            del model
            gc.collect()
            secondary = WhisperModel(secondary_name, device="cpu", compute_type="int8",
                                     cpu_threads=max(1, settings.asr_cpu_threads),
                                     num_workers=max(1, settings.asr_workers),
                                     download_root=str(settings.model_cache_dir))
            secondary_segments, _ = secondary.transcribe(
                str(audio_path), language="hi" if final_language in {"hi", "ur"} else requested_language,
                task="transcribe", vad_filter=True, beam_size=2, word_timestamps=True,
                condition_on_previous_text=False, temperature=0,
                **language_context("hi" if final_language in {"hi", "ur"} else requested_language),
            )
            secondary_rows = [{"start": round(s.start, 3), "end": round(s.end, 3),
                               "text": s.text.strip()} for s in secondary_segments if s.text.strip()]
            agreement = transcript_agreement(verified, secondary_rows)
            agreement_score = agreement["score"]
            segment_verification = verify_segments(verified, secondary_rows)
            if settings.require_asr_consensus and (not agreement["accepted"] or not segment_verification["accepted"]):
                raise RuntimeError(
                    f"Transcript needs review: independent ASR agreement was {agreement_score:.0%} with "
                    f"{segment_verification['coverage']:.0%} verified speech. No clips were created."
                )
            if segment_verification["accepted"]:
                verified = segment_verification["segments"]
        elif settings.require_asr_consensus:
            raise RuntimeError("Transcript consensus is required but WHISPER_SECONDARY_MODEL is not configured.")
        verified = stabilize_word_timestamps(verified)
        alignment_backend = settings.alignment_backend.strip().lower()
        if alignment_backend == "whisperx":
            # Avoid overlapping faster-whisper model memory with PyTorch/WhisperX.
            if "secondary_segments" in locals():
                del secondary_segments
            if "secondary" in locals():
                del secondary
            if "decode" in locals():
                del decode
            if "model" in locals():
                del model
            gc.collect()
            # Imported only in ASR_MODE=local, so API workers never import torch/WhisperX.
            from .forced_alignment import force_align_whisperx
            verified = force_align_whisperx(audio_path, verified, final_language, settings.model_cache_dir)
        elif settings.require_forced_alignment:
            raise RuntimeError(
                "Forced alignment is required, but ALIGNMENT_BACKEND is not set to whisperx."
            )
        if sum(float(s["end"])-float(s["start"]) for s in verified) < min_clean_seconds:
            raise RuntimeError("Transcript needs review: too little speech remained after timestamp stabilization.")
        verified = attach_provenance(verified, "faster-whisper", model_name, agreement_score)
        roman_hindi = settings.hindi_caption_script == "roman" and final_language in {"hi", "ur"}
        return final_language, add_roman_display_text(verified, roman_hindi)

    try:
        language, rows = await asyncio.to_thread(run)
        if not rows:
            raise RuntimeError("No clear speech was detected. Use a video with audible dialogue and less background music.")
        if not speech_regions:
            raise RuntimeError("Speech activity analysis could not verify spoken regions. Try clearer dialogue with less background noise.")
        rows[0]["speech_activity_version"] = SPEECH_ACTIVITY_VERSION
        rows[0]["speech_regions"] = speech_regions
        return language, rows
    except RuntimeError:
        raise
    except Exception as exc:
        detail = str(exc).strip() or type(exc).__name__
        raise RuntimeError(
            f"Whisper could not load or transcribe model '{model_name}': {detail}. "
            "Keep internet on for the first model download and restart the backend. Accuracy mode intentionally does not fall back to tiny models."
        ) from exc
    finally:
        audio_path.unlink(missing_ok=True)


async def _transcribe_api_impl(video_path: Path, language_hint: str, request_id: str = "", asr_route: str = "legacy", *, generated_dialogue: bool = False) -> tuple[str, list[dict[str, Any]]]:
    """Use server-side providers while retaining ClipKaro's existing safety gates.

    Local WhisperX is deliberately not invoked here: provider word timestamps are
    accepted only after the same hallucination/noise/timestamp checks.
    """
    settings = get_settings()
    # Cartoon Studio aligns one synthetic speech line at a time.
    min_clean_seconds = 0.1 if generated_dialogue else 20.0
    audio_path = video_path.with_suffix(".asr.flac")
    chunk_dir = audio_path.with_suffix(".chunks")
    await extract_api_audio(video_path, audio_path)
    try:
        duration = await probe_audio_duration(audio_path)
        if duration > settings.asr_api_max_audio_minutes * 60:
            raise RuntimeError(f"Audio is {duration / 60:.1f} minutes; API ASR limit is {settings.asr_api_max_audio_minutes} minutes. Split the source and retry.")
        speech_regions = await asyncio.to_thread(detect_speech_regions, audio_path)
        # A ten-minute FLAC is safe for the legacy API providers but can exceed
        # the practical batch response window for Scribe v2.  Keep the general
        # API limit unchanged and make only the already-selected Stage-1 route
        # use its documented five-minute chunking recommendation.
        chunk_seconds = settings.asr_chunk_seconds
        if asr_route == "elevenlabs_roman":
            chunk_seconds = min(chunk_seconds, max(30, settings.elevenlabs_asr_chunk_seconds))
        chunks = await chunk_api_audio(audio_path, duration=duration, output_dir=chunk_dir, chunk_seconds=chunk_seconds, overlap_seconds=settings.asr_chunk_overlap_seconds, max_chunks=settings.asr_api_max_chunks, max_bytes=settings.asr_api_max_chunk_mb * 1024 * 1024)

        async def transcribe_chunks(hint: str):
            results = [
                (
                    await transcribe_api(
                        chunk,
                        language_hint=hint,
                        duration=chunk_duration,
                        request_id=request_id,
                        asr_route=asr_route,
                    ),
                    offset,
                )
                for chunk, offset, chunk_duration in chunks
            ]
            return merge_chunk_results(results)

        try:
            result = await transcribe_chunks(language_hint)
        except ASRProviderError as exc:
            # Authentication and configuration errors are deliberately
            # fail-closed in the provider layer.  Do not present those as a
            # transient outage: retrying a user's upload cannot repair an
            # invalid server-side credential, and must not spend fallback
            # quota trying to hide it.
            if exc.status_code in {401, 403}:
                raise RuntimeError(
                    "The transcription service needs administrator attention. "
                    "Please try again after its server-side credential is updated."
                ) from exc
            raise RuntimeError("API transcription provider is unavailable. Retry this job later.") from exc
        final_language = "hi" if result.language == "ur" and settings.auto_language_bias == "india" else result.language
        verified = result.segments
        if not verified:
            raise RuntimeError("API transcription did not include segment timestamps; no clips were created.")
        assessment = assess_transcript(verified, final_language, min_clean_seconds=min_clean_seconds)
        normalized_hint = language_hint.strip().lower().replace("-", "_")
        if (
            not assessment["accepted"]
            and "foreign_script" in assessment["flags"]
            and normalized_hint in {"", "auto", "hinglish", "roman_hinglish"}
            and asr_route == "legacy"
        ):
            # Hindi and Urdu are acoustically close. Auto-detection can return
            # Urdu-script text for clearly Hindi speech; relabelling that result
            # as Hindi is not enough because the transcript itself remains in
            # the wrong script. Retry once with an explicit Hindi hint, then
            # keep whichever result passes more of ClipKaro's quality gate.
            try:
                hindi_result = await transcribe_chunks("hi")
                hindi_language = "hi" if hindi_result.language in {"hi", "ur"} else hindi_result.language
                hindi_assessment = assess_transcript(hindi_result.segments, hindi_language, min_clean_seconds=min_clean_seconds)
                if hindi_assessment["accepted"] or hindi_assessment["clean_duration"] > assessment["clean_duration"]:
                    result = hindi_result
                    final_language = hindi_language
                    verified = hindi_result.segments
                    assessment = hindi_assessment
            except ASRProviderError:
                pass
        if not assessment["accepted"]:
            flags = ", ".join(assessment["flags"]) or "insufficient reliable speech"
            raise RuntimeError(f"Transcript quality verification failed ({flags}). No clips were created. Try clearer audio or choose the correct language.")
        verified = stabilize_word_timestamps(assessment["segments"])
        if not any(segment.get("words") for segment in verified):
            raise RuntimeError("API transcription did not include word timestamps; verified caption export is blocked.")
        if sum(float(s["end"])-float(s["start"]) for s in verified) < min_clean_seconds:
            raise RuntimeError("Transcript needs review: too little speech remained after timestamp stabilization.")
        verified = attach_provenance(verified, result.provider, result.model, None)
        for segment in verified:
            segment["asr_provider"] = result.provider
            segment["asr_fallback_used"] = result.fallback_used
            segment["timestamp_quality"] = result.timestamp_quality
        # Persist ASR observability to the first segment (metadata carrier)
        if verified:
            verified[0]["asr_route"] = asr_route
            verified[0]["primary_provider"] = result.primary_provider
            verified[0]["final_provider"] = result.final_provider
            verified[0]["provider_attempt_count"] = result.provider_attempt_count
            verified[0]["retry_count"] = result.retry_count
            verified[0]["fallback_used"] = result.fallback_used
            verified[0]["fallback_provider"] = result.fallback_provider
            verified[0]["fallback_reason_category"] = result.fallback_reason_category
            verified[0]["total_asr_latency_ms"] = round(result.provider_latency * 1000)
            verified[0]["asr_success"] = result.asr_success
            verified[0]["timing_source"] = "PROVIDER_NATIVE_WORD"
            # Store attempts trace as JSON string to avoid bloating segment objects
            if result.attempts_trace:
                verified[0]["provider_attempts_trace"] = json.dumps(result.attempts_trace, separators=(",", ":"))
        if not speech_regions:
            raise RuntimeError("Speech activity analysis could not verify spoken regions. Try clearer dialogue with less background noise.")
        verified[0]["speech_activity_version"] = SPEECH_ACTIVITY_VERSION
        verified[0]["speech_regions"] = speech_regions
        # The Roman V3 -> Display V1 chain is a Hinglish-only, operator-enabled
        # candidate.  It is never applied to legacy fallback output or Hindi /
        # Marathi jobs, and it leaves native word start/end values unchanged.
        if (
            language_hint.strip().lower().replace("-", "_") in {"hinglish", "roman_hinglish"}
            and result.provider == "elevenlabs"
            and asr_route == "elevenlabs_roman"
        ):
            verified = apply_roman_v3_display_v1(verified)
        roman_hindi = settings.hindi_caption_script == "roman" and final_language in {"hi", "ur"}
        return final_language, add_roman_display_text(verified, roman_hindi and result.provider != "elevenlabs")
    finally:
        audio_path.unlink(missing_ok=True)
        shutil.rmtree(chunk_dir, ignore_errors=True)

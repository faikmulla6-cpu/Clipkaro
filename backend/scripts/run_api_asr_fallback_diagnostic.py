#!/usr/bin/env python3
"""Controlled real Cloudflare fallback diagnostic; not part of WER corpus."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from app.core.config import get_settings  # noqa: E402
from app.services import asr_providers  # noqa: E402
from app.services.asr_benchmark import probe_duration  # noqa: E402
from app.services.video import extract_api_audio  # noqa: E402


async def main() -> int:
    source = ROOT / "stress_corpus" / "cases" / "vaani-hi-01.wav"
    prepared = source.with_suffix(".fallback-diagnostic.flac")
    calls = {"groq": 0, "cloudflare": 0}
    original_groq = asr_providers.GroqASRProvider.transcribe
    original_cloudflare = asr_providers.CloudflareASRProvider.transcribe
    async def injected_groq(*args, **kwargs):
        calls["groq"] += 1
        raise asr_providers.ASRProviderError("controlled diagnostic outage", retryable=True, status_code=503)
    async def counted_cloudflare(self, *args, **kwargs):
        calls["cloudflare"] += 1
        return await original_cloudflare(self, *args, **kwargs)
    settings = get_settings(); old_primary, old_fallback = settings.asr_primary_provider, settings.asr_fallback_provider
    try:
        settings.asr_primary_provider, settings.asr_fallback_provider = "groq", "cloudflare"
        await extract_api_audio(source, prepared)
        asr_providers.GroqASRProvider.transcribe = injected_groq
        asr_providers.CloudflareASRProvider.transcribe = counted_cloudflare
        result = await asr_providers.transcribe_api(prepared, language_hint="hi", duration=probe_duration(source), request_id="step2b-controlled-fallback")
        payload = {"diagnostic": True, "groq_attempts": calls["groq"], "cloudflare_attempts": calls["cloudflare"], "final_provider": result.provider,
                   "fallback_used": result.fallback_used, "authoritative_transcript_count": 1, "segments": len(result.segments), "words": len(result.words),
                   "passed": calls == {"groq": 1, "cloudflare": 1} and result.provider == "cloudflare" and result.fallback_used}
        target = ROOT / "asr-qualification-evidence" / "api-step2b-2026-08-13" / "fallback-orchestration-diagnostic.json"
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload)); return 0 if payload["passed"] else 1
    finally:
        settings.asr_primary_provider, settings.asr_fallback_provider = old_primary, old_fallback
        asr_providers.GroqASRProvider.transcribe = original_groq
        asr_providers.CloudflareASRProvider.transcribe = original_cloudflare
        prepared.unlink(missing_ok=True)

if __name__ == "__main__": raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""Manual, opt-in API ASR smoke test. Requires private environment credentials."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.asr_providers import transcribe_api
from app.services.video import probe_audio_duration

async def main() -> int:
    path = Path(os.environ.get("API_ASR_SMOKE_AUDIO", "")).expanduser()
    if not path.is_file():
        print("Set API_ASR_SMOKE_AUDIO to a tiny private FLAC/WAV sample.", file=sys.stderr); return 2
    result = await transcribe_api(path, language_hint=os.environ.get("API_ASR_SMOKE_LANGUAGE", "auto"), duration=await probe_audio_duration(path))
    print({"provider": result.provider, "model": result.model, "language": result.language, "text": result.text[:300], "segments": len(result.segments), "words": len(result.words), "latency_seconds": result.provider_latency, "fallback_used": result.fallback_used})
    return 0
raise SystemExit(asyncio.run(main()))

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


SYSTEM_URDU_TTS_MODEL = "system/edge-tts-urdu"
SYSTEM_REGIONAL_TTS_MODEL = "system/edge-tts-regional"
SYSTEM_EDGE_TTS_MODELS = {SYSTEM_URDU_TTS_MODEL, SYSTEM_REGIONAL_TTS_MODEL}
KOKORO_TTS_MODEL = "hexgrad/kokoro-82m"
SYSTEM_KOKORO_TTS_MODEL = "system/kokoro-82m"
KOKORO_VOICES = {"en": ["af_heart", "af_bella", "am_adam"], "hi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"]}
EDGE_VOICES = {
    "ur": {
        "female": "ur-PK-UzmaNeural",
        "male": "ur-PK-AsadNeural",
        "neutral": "ur-PK-UzmaNeural",
        "child": "ur-PK-UzmaNeural",
        "elder": "ur-PK-UzmaNeural",
    },
    "hi": {
        "female": "hi-IN-SwaraNeural",
        "male": "hi-IN-MadhurNeural",
        "neutral": "hi-IN-SwaraNeural",
        "child": "hi-IN-SwaraNeural",
        "elder": "hi-IN-SwaraNeural",
    },
    "mr": {
        "female": "mr-IN-AarohiNeural",
        "male": "mr-IN-ManoharNeural",
        "neutral": "mr-IN-AarohiNeural",
    },
    "en": {
        "female": "en-US-JennyNeural",
        "male": "en-US-GuyNeural",
        "neutral": "en-US-AriaNeural",
        "child": "en-US-AnaNeural",
        "elder": "en-US-JennyNeural",
    },
}


def cartoon_tts_for_language(model: str, language: str) -> str:
    if language == "ur" and model in {"", KOKORO_TTS_MODEL}:
        return SYSTEM_URDU_TTS_MODEL
    return model


def system_urdu_tts_model_row() -> dict[str, Any]:
    return {
        "id": SYSTEM_URDU_TTS_MODEL,
        "name": "Built-in Urdu voices",
        "supported_voices": ["ur-PK-UzmaNeural", "ur-PK-AsadNeural"],
        "languages": ["ur"],
        "description": "Built-in Urdu voices with native word timestamps for synchronized captions. Uses the external Edge speech service; availability can vary.",
    }


def built_in_voice_models() -> list[dict[str, Any]]:
    return [
        {
            "id": SYSTEM_KOKORO_TTS_MODEL,
            "name": "Built-in Kokoro",
            "supported_voices": [voice for voices in KOKORO_VOICES.values() for voice in voices],
            "voices_by_language": KOKORO_VOICES,
            "languages": list(KOKORO_VOICES),
            "description": "English and Hindi voices generated on ClipKaro's render worker.",
        },
        system_urdu_tts_model_row(),
        {
            "id": SYSTEM_REGIONAL_TTS_MODEL,
            "name": "Built-in Hinglish and Marathi voices",
            "languages": ["hinglish", "mr"],
            "voices_by_language": {
                language: list(dict.fromkeys(EDGE_VOICES[locale].values()))
                for language, locale in (("hinglish", "hi"), ("mr", "mr"))
            },
            "description": "Built-in speech for Hinglish and Marathi.",
        },
    ]


def built_in_voice_selection(model: str, language: str) -> str:
    if not model or model == KOKORO_TTS_MODEL:
        if language == "ur":
            return SYSTEM_URDU_TTS_MODEL
        if language in {"hinglish", "mr"}:
            return SYSTEM_REGIONAL_TTS_MODEL
        return SYSTEM_KOKORO_TTS_MODEL
    return model


def system_voice_for(language: str, voice_type: str = "neutral") -> str | None:
    lang = str(language or "").lower().split("-", 1)[0]
    kind = str(voice_type or "neutral").lower()
    return EDGE_VOICES.get(lang, {}).get(kind) or EDGE_VOICES.get(lang, {}).get("neutral")


async def synthesize_edge_tts(
    text: str,
    voice: str,
    output_path: Path,
    *,
    rate: str = "-8%",
    volume: str = "-8%",
    pitch: str = "-3Hz",
    attempts: int = 3,
) -> list[dict[str, Any]]:
    """Synthesize speech and capture native Edge TTS WordBoundary events with bounded retries."""
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("The system TTS adapter is not installed in this renderer.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(max(1, min(3, attempts))):
        boundaries: list[dict[str, Any]] = []
        communicate = edge_tts.Communicate(
            text=str(text),
            voice=str(voice),
            rate=rate,
            volume=volume,
            pitch=pitch,
            boundary="WordBoundary",
        )
        try:
            with output_path.open("wb") as audio_file:
                async for chunk in communicate.stream():
                    if chunk.get("type") == "audio":
                        audio_file.write(chunk.get("data") or b"")
                    elif chunk.get("type") == "WordBoundary":
                        boundaries.append({
                            "type": "WordBoundary",
                            "offset": int(chunk.get("offset") or 0),
                            "duration": int(chunk.get("duration") or 0),
                            "text": str(chunk.get("text") or ""),
                        })
            if not output_path.is_file() or output_path.stat().st_size < 128:
                raise RuntimeError("The system speech service returned an empty audio file.")
            if not boundaries:
                raise RuntimeError("The system speech service returned audio without word timing metadata.")
            return boundaries
        except Exception as exc:
            last_error = exc
            output_path.unlink(missing_ok=True)
            if attempt + 1 < max(1, min(3, attempts)):
                await asyncio.sleep(0.8 * (attempt + 1))

    raise RuntimeError(
        "The built-in speech service could not generate this voice. Please retry shortly."
    ) from last_error

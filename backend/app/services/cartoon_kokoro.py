"""CPU inference for the pinned, self-hosted Kokoro voice model."""
import asyncio
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
from threading import Lock

from .cartoon_speech import KOKORO_VOICES

MODEL_DIRECTORY = Path(os.environ.get("CARTOON_KOKORO_MODEL_DIR", "/opt/clipkaro/kokoro"))
_inference_lock = Lock()


@lru_cache(maxsize=1)
def _model():
    from kokoro import KModel

    return KModel(config=str(MODEL_DIRECTORY / "config.json"),
                  model=str(MODEL_DIRECTORY / "kokoro-v1_0.pth")).eval()


@lru_cache(maxsize=2)
def _pipeline(language: str):
    from kokoro import KPipeline

    return KPipeline(lang_code={"en": "a", "hi": "h"}[language], model=_model(), device="cpu")


def _render(text: str, voice: str, output: Path) -> list[dict]:
    import numpy as np

    language = next((lang for lang, voices in KOKORO_VOICES.items() if voice in voices), None)
    ffmpeg = shutil.which("ffmpeg")
    if language is None or not ffmpeg:
        raise RuntimeError("The built-in Kokoro voice is unavailable.")
    chunks, words = [], []
    offset = 0.0
    with _inference_lock:
        for result in _pipeline(language)(text, voice=str(MODEL_DIRECTORY / "voices" / f"{voice}.pt")):
            if result.audio is None or not result.audio.numel():
                continue
            samples = result.audio.detach().cpu().numpy().astype("<f4", copy=False)
            chunks.append(samples)
            for token in result.tokens or []:
                start, end = token.start_ts, token.end_ts
                if token.text.strip() and start is not None and end is not None and end > start:
                    words.append({"text": token.text, "offset": round((offset + start) * 10_000_000),
                                  "duration": round((end - start) * 10_000_000)})
            offset += len(samples) / 24000
    if not chunks:
        raise RuntimeError("Kokoro returned no speech.")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-v", "error", "-y", "-f", "f32le", "-ar", "24000", "-ac", "1",
         "-i", "pipe:0", "-codec:a", "libmp3lame", "-q:a", "4", str(output)],
        input=np.concatenate(chunks).tobytes(), capture_output=True, check=True, timeout=45,
    )
    return words


async def synthesize_kokoro(text: str, voice: str, output: Path) -> list[dict]:
    try:
        return await asyncio.to_thread(_render, text, voice, output)
    except (ImportError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError("ClipKaro could not generate this built-in voice. You can render with captions only.") from exc

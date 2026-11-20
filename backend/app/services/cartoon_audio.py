from __future__ import annotations

import asyncio
import math
import shutil
import subprocess
from array import array
from pathlib import Path
from typing import Iterable


def rms_envelope_from_samples(
    samples: Iterable[float],
    *,
    sample_rate: int = 48_000,
    fps: int = 60,
) -> list[float]:
    """Create a normalized, smoothed RMS envelope with one value per animation frame."""
    values = list(samples)
    if not values or sample_rate <= 0 or fps <= 0:
        return []
    frame_size = max(1, sample_rate // fps)
    rms_values: list[float] = []
    for offset in range(0, len(values), frame_size):
        chunk = values[offset:offset + frame_size]
        if not chunk:
            continue
        rms = math.sqrt(sum(float(value) * float(value) for value in chunk) / len(chunk))
        rms_values.append(rms)
    if not rms_values:
        return []
    ordered = sorted(rms_values)
    peak = ordered[min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))]
    if peak <= 1e-7:
        return [0.0] * len(rms_values)
    gate = peak * 0.035
    scale = max(peak * 1.15, gate + 1e-7)
    normalized = [0.0 if value < gate else min(1.0, (value - gate) / (scale - gate)) for value in rms_values]
    smoothed: list[float] = []
    previous = 0.0
    for value in normalized:
        coefficient = 0.62 if value > previous else 0.32
        previous += (value - previous) * coefficient
        smoothed.append(round(max(0.0, min(1.0, previous)), 4))
    return smoothed


async def build_lip_envelope(audio_path: Path, *, fps: int = 60) -> list[float]:
    """Decode a speech asset to mono float PCM and calculate its frame-accurate RMS envelope."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(audio_path),
                "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []
    pcm = array("f")
    try:
        pcm.frombytes(proc.stdout)
    except (ValueError, OverflowError):
        return []
    return rms_envelope_from_samples(pcm, sample_rate=48_000, fps=fps)

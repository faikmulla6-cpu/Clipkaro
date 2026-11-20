from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np


def _smooth_noise(rng: np.random.Generator, count: int, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    noise = rng.normal(0.0, 1.0, count)
    frequencies = np.fft.rfftfreq(count, 1.0 / sample_rate)
    filtered = np.fft.rfft(noise) * np.exp(-np.square(frequencies / cutoff_hz))
    return np.fft.irfft(filtered, count)


def _save_stereo_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim == 1:
        values = np.column_stack((values, values))
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("Audio stems must be mono or stereo PCM arrays.")
    pcm = (np.clip(values, -0.95, 0.95) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def build_jannat_audio_stems(
    output_dir: Path,
    *,
    duration_seconds: int = 30,
    sample_rate: int = 48_000,
    seed: int = 2038,
) -> dict[str, Path | int]:
    """Create the reference's original restrained score and bedroom foley as editable WAV stems."""
    if duration_seconds != 30:
        raise ValueError("The Jannat reference score and foley are authored for a 30-second episode.")
    if sample_rate != 48_000:
        raise ValueError("The Jannat reference audio stems require a 48 kHz sample rate.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    count = sample_rate * duration_seconds
    timeline = np.arange(count, dtype=np.float64) / sample_rate

    # Restrained original D-minor score: bowed drone, soft felt notes, unresolved ending.
    score = np.zeros((count, 2), dtype=np.float64)
    for index, frequency in enumerate((73.416, 110.0, 146.832, 164.814, 220.0)):
        voice = np.zeros_like(timeline)
        modulation = 0.16 * np.sin(2.0 * np.pi * 0.13 * timeline + index)
        for harmonic in (1, 2, 3, 4):
            voice += np.sin(2.0 * np.pi * frequency * harmonic * timeline + modulation) / (harmonic * harmonic)
        voice *= 0.009 * (0.73 + 0.27 * np.sin(2.0 * np.pi * 0.073 * timeline + index))
        score[:, 0] += voice
        score[:, 1] += np.roll(voice, int(sample_rate * 0.003 * (index + 1)))

    for at, frequency in (
        (1.0, 293.665), (5.7, 261.626), (9.7, 220.0), (14.8, 293.665),
        (16.1, 349.228), (18.2, 329.628), (22.0, 220.0), (25.2, 233.082),
        (28.4, 293.665),
    ):
        elapsed = np.maximum(0.0, timeline - at)
        active = timeline >= at
        envelope = (1.0 - np.exp(-elapsed * 32.0)) * np.exp(-elapsed / 2.0) * active
        note = np.zeros_like(timeline)
        for harmonic in (1, 2, 3, 4, 5):
            note += np.sin(2.0 * np.pi * frequency * harmonic * elapsed) * np.exp(-elapsed * harmonic * 0.26) / (harmonic * harmonic)
        note *= envelope * 0.027
        score[:, 0] += note
        score[:, 1] += note * 0.88
        for delay, amplitude in ((0.19, 0.18), (0.41, 0.10), (0.67, 0.06)):
            shift = int(delay * sample_rate)
            if shift < count:
                score[shift:, 1] += note[:-shift] * amplitude

    rise = np.clip((timeline - 22.0) / 8.0, 0.0, 1.0)
    for index, frequency in enumerate((146.83, 155.56, 293.66)):
        voice = np.sin(2.0 * np.pi * frequency * timeline + 0.08 * np.sin(2.0 * np.pi * 4.5 * timeline))
        score[:, index % 2] += voice * 0.007 * rise
    fade = np.minimum(timeline / 1.8, 1.0) * np.minimum((duration_seconds - timeline) / 0.35, 1.0)
    score *= fade[:, None]
    score_path = output_dir / "score.wav"
    _save_stereo_wav(score_path, score, sample_rate)

    # Original bedroom ambience and foley; intentionally quiet under the dialogue.
    foley = np.zeros(count, dtype=np.float64)
    foley += _smooth_noise(rng, count, 350.0, sample_rate) * 0.009

    def add_event(at: float, samples: np.ndarray) -> None:
        start = int(round(at * sample_rate))
        if start < 0 or start >= count:
            return
        length = min(len(samples), count - start)
        if length > 0:
            foley[start:start + length] += samples[:length]

    for at, duration, level in (
        (2.26, 0.48, 0.18), (3.0, 0.75, 0.06), (5.2, 0.9, 0.035),
        (7.0, 0.72, 0.025), (13.5, 0.8, 0.045), (18.4, 0.65, 0.032),
        (24.9, 1.1, 0.023), (28.0, 1.0, 0.02),
    ):
        local_time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
        noise = (
            _smooth_noise(rng, len(local_time), 2600.0, sample_rate)
            - _smooth_noise(rng, len(local_time), 150.0, sample_rate)
        )
        add_event(at, noise * np.power(np.sin(np.pi * local_time / duration), 1.6) * level)

    for at, duration in ((2.7, 0.65), (18.6, 1.3), (20.2, 0.7), (21.4, 0.8)):
        local_time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
        noise = _smooth_noise(rng, len(local_time), 1100.0, sample_rate)
        add_event(at, noise * np.square(np.sin(np.pi * local_time / duration)) * 0.12)

    for at in (21.2, 22.65):
        local_time = np.arange(int(sample_rate * 0.65), dtype=np.float64) / sample_rate
        creak = 0.015 * np.sin(2.0 * np.pi * (280.0 * local_time + 13.0 * np.sin(local_time * 12.0)))
        add_event(at, creak * np.power(np.sin(np.pi * local_time / 0.65), 3))
        thump_time = np.arange(int(sample_rate * 0.17), dtype=np.float64) / sample_rate
        add_event(at, 0.033 * np.sin(2.0 * np.pi * 65.0 * thump_time) * np.exp(-thump_time * 26.0))

    for at in (27.05, 27.19):
        local_time = np.arange(int(sample_rate * 0.14), dtype=np.float64) / sample_rate
        click = (
            np.sin(2.0 * np.pi * 900.0 * local_time) * 0.032
            + np.sin(2.0 * np.pi * 1810.0 * local_time) * 0.008
        ) * np.exp(-local_time * 55.0)
        add_event(at, click)

    foley_path = output_dir / "foley.wav"
    _save_stereo_wav(foley_path, foley, sample_rate)

    metadata = {
        "generator": "ClipKaro original deterministic Jannat score and bedroom foley",
        "seed": seed,
        "sample_rate": sample_rate,
        "channels": 2,
        "duration_seconds": duration_seconds,
        "score": {"filename": score_path.name, "format": "PCM s16le WAV", "role": "restrained D-minor suspense score"},
        "foley": {"filename": foley_path.name, "format": "PCM s16le WAV", "role": "bedroom ambience, sheets, movement, footsteps and door-knob cues"},
        "note": "Original procedural audio; no external music or sound-effect asset is used.",
    }
    (output_dir / "audio-stems.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"score_path": score_path, "foley_path": foley_path, "duration_seconds": duration_seconds, "sample_rate": sample_rate}

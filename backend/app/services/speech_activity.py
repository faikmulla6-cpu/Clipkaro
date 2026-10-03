from __future__ import annotations

import logging
import subprocess
from collections import deque
from pathlib import Path
from typing import Iterable

import webrtcvad

from app.core.config import get_settings
from .video import find_media_tool

logger = logging.getLogger("clipkaro.speech_activity")

SPEECH_ACTIVITY_VERSION = "webrtc-vad-20ms-v1"
SAMPLE_RATE = 16_000
FRAME_MS = 20
FRAME_SECONDS = FRAME_MS / 1000.0
SAMPLE_WIDTH_BYTES = 2
START_WINDOW_FRAMES = 4
START_VOICED_FRAMES = 3
STOP_SILENT_FRAMES = 5
START_PAD_SECONDS = 0.04
END_PAD_SECONDS = 0.06
MERGE_GAP_SECONDS = 0.04


def _regions_from_voicing(
    flags: Iterable[bool],
    *,
    frame_seconds: float = FRAME_SECONDS,
    start_window_frames: int = START_WINDOW_FRAMES,
    start_voiced_frames: int = START_VOICED_FRAMES,
    stop_silent_frames: int = STOP_SILENT_FRAMES,
    start_pad_seconds: float = START_PAD_SECONDS,
    end_pad_seconds: float = END_PAD_SECONDS,
    merge_gap_seconds: float = MERGE_GAP_SECONDS,
) -> list[dict[str, float]]:
    """Turn frame-level VAD decisions into stable speech regions."""
    decisions = list(bool(item) for item in flags)
    if not decisions:
        return []

    pre_roll: deque[tuple[float, float, bool]] = deque(maxlen=max(1, start_window_frames))
    regions: list[dict[str, float]] = []
    active = False
    region_start = 0.0
    last_voiced_end = 0.0
    silent_run = 0

    for index, voiced in enumerate(decisions):
        frame_start = index * frame_seconds
        frame_end = frame_start + frame_seconds

        if not active:
            pre_roll.append((frame_start, frame_end, voiced))
            if (
                len(pre_roll) == max(1, start_window_frames)
                and sum(1 for _, _, item in pre_roll if item) >= max(1, start_voiced_frames)
            ):
                first_voiced = next((start for start, _, item in pre_roll if item), frame_start)
                voiced_ends = [end for _, end, item in pre_roll if item]
                region_start = max(0.0, first_voiced - max(0.0, start_pad_seconds))
                last_voiced_end = max(voiced_ends) if voiced_ends else frame_end
                active = True
                silent_run = 0
                pre_roll.clear()
            continue

        if voiced:
            last_voiced_end = frame_end
            silent_run = 0
        else:
            silent_run += 1

        if silent_run >= max(1, stop_silent_frames):
            region_end = min(
                len(decisions) * frame_seconds,
                last_voiced_end + max(0.0, end_pad_seconds),
            )
            if region_end > region_start:
                regions.append({"start": region_start, "end": region_end})
            active = False
            silent_run = 0
            pre_roll.clear()

    if active:
        region_end = min(
            len(decisions) * frame_seconds,
            last_voiced_end + max(0.0, end_pad_seconds),
        )
        if region_end > region_start:
            regions.append({"start": region_start, "end": region_end})

    merged: list[dict[str, float]] = []
    for region in regions:
        if (
            merged
            and float(region["start"]) - float(merged[-1]["end"]) <= max(0.0, merge_gap_seconds)
        ):
            merged[-1]["end"] = max(float(merged[-1]["end"]), float(region["end"]))
        else:
            merged.append({"start": float(region["start"]), "end": float(region["end"])})

    return [
        {"start": round(region["start"], 3), "end": round(region["end"], 3)}
        for region in merged
        if region["end"] > region["start"]
    ]


def detect_speech_regions(audio_path: Path, aggressiveness: int = 2) -> list[dict[str, float]]:
    """Detect human speech with WebRTC VAD from any FFmpeg-readable audio source."""
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for speech activity analysis.")

    timeout = max(30, int(get_settings().media_process_timeout_seconds))
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(audio_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Speech activity analysis exceeded the media safety limit.") from exc

    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="ignore")[-500:]
        raise RuntimeError(f"Speech activity analysis could not decode audio: {detail}")

    pcm = proc.stdout
    frame_bytes = int(SAMPLE_RATE * FRAME_MS / 1000) * SAMPLE_WIDTH_BYTES
    if frame_bytes <= 0 or len(pcm) < frame_bytes:
        return []

    vad = webrtcvad.Vad(max(0, min(int(aggressiveness), 3)))
    flags: list[bool] = []
    for offset in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        frame = pcm[offset : offset + frame_bytes]
        try:
            flags.append(bool(vad.is_speech(frame, SAMPLE_RATE)))
        except Exception:
            logger.exception("webrtc_vad_frame_failed offset=%s", offset)
            flags.append(False)

    return _regions_from_voicing(flags)

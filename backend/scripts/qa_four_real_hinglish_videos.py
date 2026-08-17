#!/usr/bin/env python3
"""Isolated four-video ElevenLabs + Roman caption pipeline QA.

This is deliberately a staging-only harness.  It transcribes exactly one
deterministic 90 second window per user-authorised source, persists evidence
before rendering, and calls ClipKaro's normal create_srt/render_short path.
It never modifies production ASR routing or qualification policies.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.rendering import create_srt, render_short
from app.services.roman_hinglish_display_v1 import display_text, sha256 as display_policy_sha256
from app.services.roman_hinglish_policy_v3 import normalize_v3, policy_sha256
from app.services.video import find_media_tool, probe_duration

MODEL = "scribe_v2"
URL = "https://api.elevenlabs.io/v1/speech-to-text"
WINDOW_SECONDS = 90.0
EXPORT_SECONDS = 30.0
OUT = ROOT / "asr-qualification-evidence" / "elevenlabs-roman-v3-four-real-video-qa"

# Staging-only source paths are supplied explicitly at runtime. This keeps
# developer machine paths and creator filenames out of the release source.
def qa_sources() -> list[tuple[str, Path]]:
    raw = os.getenv("CLIPKARO_QA_VIDEO_PATHS", "").strip()
    if not raw:
        raise RuntimeError(
            "CLIPKARO_QA_VIDEO_PATHS is required for this staging-only harness "
            "(use the OS path separator between up to four user-authorized files)."
        )
    paths = [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]
    if not 1 <= len(paths) <= 4:
        raise RuntimeError("CLIPKARO_QA_VIDEO_PATHS must contain between 1 and 4 media paths.")
    return [(f"real-video-{index:02d}", path) for index, path in enumerate(paths, start=1)]


EXPECTED_V3 = "2bb7ed2f8e4c32782a030cfba19deb49875c32cdf29ba70ef7ce896f96cdfbe0"
EXPECTED_DISPLAY = "92992635e56181ebdb7ac748d9df73338ab465de0330c0eb7a821c59212a424e"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def valid_word(word: dict[str, Any], duration: float) -> bool:
    try:
        return 0 <= float(word["start"]) < float(word["end"]) <= duration + 0.05 and bool(str(word["word"]).strip())
    except (KeyError, TypeError, ValueError):
        return False


async def extract_window(source: Path, audio: Path, start: float, duration: float) -> None:
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for real-video QA.")
    proc = await asyncio.to_thread(
        subprocess.run,
        [ffmpeg, "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
         "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(audio)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False, timeout=180,
    )
    if proc.returncode != 0 or not audio.exists() or audio.stat().st_size == 0:
        audio.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg could not extract the deterministic QA audio window.")


def native_words(response: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(response.get("words") or []):
        if not isinstance(raw, dict) or raw.get("type", "word") != "word":
            continue
        text = str(raw.get("text") or raw.get("word") or "").strip()
        try:
            start, end = float(raw.get("start")), float(raw.get("end"))
        except (TypeError, ValueError):
            start, end = -1.0, -1.0
        item: dict[str, Any] = {"index": index, "word": text, "start": start, "end": end}
        for field in ("confidence", "speaker", "type", "language"):
            if field in raw:
                item[field] = raw[field]
        result.append(item)
    return result


def word_map(words: list[dict[str, Any]], offset: float, duration: float) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for item in words:
        # Providers may include a bounded number of zero-length word records.
        # They count against native-timing coverage but cannot be rendered as
        # caption events, so never pass them to create_srt.
        if not valid_word(item, duration):
            continue
        v3_word = normalize_v3(str(item["word"]))
        if not v3_word:
            continue
        display_word = display_text(v3_word)
        mapped.append({
            "raw_word": item["word"], "v3_word": v3_word, "display_word": display_word,
            "start": round(float(item["start"]) + offset, 6),
            "end": round(float(item["end"]) + offset, 6),
            "timing_source": "ELEVENLABS_NATIVE_WORD" if len(v3_word.split()) == 1 else "ELEVENLABS_NATIVE_SPAN",
        })
    return mapped


async def transcribe(video_id: str, source: Path, timeline_path: Path) -> dict[str, Any]:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured in the ignored local environment.")
    source_duration = await probe_duration(source)
    window_duration = min(WINDOW_SECONDS, source_duration)
    window_start = 0.0 if source_duration <= 120 else round((source_duration - window_duration) / 2, 3)
    video_sha = sha256_file(source)
    audio = timeline_path.with_suffix(".flac")
    await extract_window(source, audio, window_start, window_duration)
    try:
        started = time.perf_counter()
        with audio.open("rb") as handle:
            async with httpx.AsyncClient(timeout=max(180, settings.asr_provider_timeout_seconds)) as client:
                response = await client.post(
                    URL, headers={"xi-api-key": settings.elevenlabs_api_key},
                    data={"model_id": MODEL, "timestamps_granularity": "word", "tag_audio_events": "false", "file_format": "other"},
                    files={"file": (audio.name, handle, "audio/flac")},
                )
        response.raise_for_status()
        raw = response.json()
        words = native_words(raw)
        coverage = sum(valid_word(word, window_duration) for word in words) / len(words) if words else 0.0
        timeline = {
            "video_id": video_id, "source_video": source.name, "source_video_sha256": video_sha,
            "source_duration_seconds": source_duration, "window_start_seconds": window_start,
            "window_duration_seconds": window_duration, "audio_sha256": sha256_file(audio),
            "provider": "elevenlabs", "model": MODEL, "language_code": raw.get("language_code"),
            "language_probability": raw.get("language_probability"), "transcript": str(raw.get("text") or ""),
            "native_words": words, "native_timing_coverage": coverage,
            "latency_seconds": round(time.perf_counter() - started, 3), "retry_count": 0,
        }
        write_json(timeline_path, timeline)
        reloaded = json.loads(timeline_path.read_text(encoding="utf-8"))
        if reloaded != timeline:
            raise RuntimeError("Persisted native timeline did not reload identically.")
        timeline["timeline_sha256"] = sha256_file(timeline_path)
        timeline["native_timeline_reload_valid"] = True
        if not timeline["transcript"] or not words or coverage < 0.95:
            raise RuntimeError("ElevenLabs returned insufficient usable native word timing.")
        return timeline
    finally:
        audio.unlink(missing_ok=True)


def verify_export(path: Path) -> dict[str, Any]:
    ffprobe = find_media_tool("ffprobe")
    ffmpeg = find_media_tool("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError("FFmpeg and FFprobe are required for export verification.")
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=False, timeout=30)
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True, check=False, timeout=120)
    payload = json.loads(probe.stdout) if probe.returncode == 0 else {}
    stream_types = {stream.get("codec_type") for stream in payload.get("streams", [])}
    return {"exists": path.exists(), "non_empty": path.exists() and path.stat().st_size > 0,
            "ffprobe_pass": probe.returncode == 0, "decode_pass": decoded.returncode == 0,
            "video_stream": "video" in stream_types, "audio_stream": "audio" in stream_types,
            "duration_seconds": float(payload.get("format", {}).get("duration", 0) or 0),
            "file_sha256": sha256_file(path) if path.exists() else None}


async def process(video_id: str, source: Path) -> dict[str, Any]:
    if not source.exists():
        raise FileNotFoundError(source)
    folder = OUT / video_id
    folder.mkdir(parents=True, exist_ok=True)
    timeline_path = folder / "native-word-timeline.json"
    if timeline_path.exists():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        if (timeline.get("source_video_sha256") != sha256_file(source)
                or not isinstance(timeline.get("native_words"), list)
                or float(timeline.get("native_timing_coverage", 0)) < 0.95):
            raise RuntimeError(f"Existing timeline for {video_id} cannot be safely resumed.")
    else:
        timeline = await transcribe(video_id, source, timeline_path)
    # Recalculate after reloading, including the persisted file hash.
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    timeline_hash = sha256_file(timeline_path)
    mapping = word_map(timeline["native_words"], float(timeline["window_start_seconds"]), float(timeline["window_duration_seconds"]))
    mapping_path = folder / "display-v1-word-map.json"
    write_json(mapping_path, {"timeline_sha256": timeline_hash, "policy_v3_sha256": policy_sha256(),
                              "display_policy_v1_sha256": display_policy_sha256(), "words": mapping})
    export_start = round(float(timeline["window_start_seconds"]) + (float(timeline["window_duration_seconds"]) - EXPORT_SECONDS) / 2, 3)
    export_end = round(export_start + EXPORT_SECONDS, 3)
    caption_words = [{"text": row["display_word"], "start": row["start"], "end": row["end"]}
                     for row in mapping if row["display_word"] and row["end"] >= export_start and row["start"] <= export_end]
    srt_path = folder / f"{video_id}-display-v1.srt"
    create_srt([{"start": export_start, "end": export_end, "text": "", "words": caption_words}], export_start, export_end, srt_path)
    output = folder / f"{video_id}-display-v1.mp4"
    await render_short(source, output, export_start, export_end, srt_path, "ClipKaro QA", False)
    validation = verify_export(output)
    result = {"video_id": video_id, "timeline_path": str(timeline_path), "timeline_sha256": timeline_hash,
              "source_video_sha256": timeline["source_video_sha256"], "source_duration_seconds": timeline["source_duration_seconds"],
              "window_start_seconds": timeline["window_start_seconds"], "window_duration_seconds": timeline["window_duration_seconds"],
              "native_word_count": len(timeline["native_words"]), "native_timing_coverage": timeline["native_timing_coverage"],
              "display_word_count": len(mapping), "caption_words_in_export": len(caption_words),
              "residual_devanagari_count": sum(any("\u0900" <= char <= "\u097f" for char in row["display_word"]) for row in mapping),
              "srt_path": str(srt_path), "export_path": str(output), "export": validation,
              # Match create_srt/timed_words exactly: boundary-spanning words are
              # clipped to the export window before clip-local validation.
              "clip_local_timestamp_valid": all(
                  0 <= max(row["start"], export_start) - export_start
                  < min(row["end"], export_end) - export_start <= EXPORT_SECONDS + .05
                  for row in mapping if row["end"] > export_start and row["start"] < export_end
              ),
              "display_v1_reached_renderer": bool(caption_words) and srt_path.exists() and srt_path.stat().st_size > 0}
    write_json(folder / "result.json", result)
    return result


async def main() -> None:
    if policy_sha256() != EXPECTED_V3 or display_policy_sha256() != EXPECTED_DISPLAY:
        raise RuntimeError("Frozen Roman policy integrity check failed.")
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for video_id, source in qa_sources():
        results.append(await process(video_id, source))
    write_json(OUT / "summary.json", {"scope": "four user-authorized real videos; staging only", "model": MODEL,
                                        "policy_v3_sha256": policy_sha256(), "display_policy_v1_sha256": display_policy_sha256(),
                                        "results": results})
    print(json.dumps({"videos": len(results), "output": str(OUT)}))


if __name__ == "__main__":
    asyncio.run(main())

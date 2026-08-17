#!/usr/bin/env python3
"""Render deterministic Display V1 QA clips from an explicitly supplied source.

This staging-only helper intentionally contains no developer-specific absolute
paths. Set CLIPKARO_QA_SOURCE_VIDEO to an authorized local media file.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.rendering import create_srt, render_short

D = ROOT / "asr-qualification-evidence/elevenlabs-roman-v3-real-video-qa"
EXPECTED_TIMELINE_SHA256 = "83722be8d5acccecc8fde46f316e242fdb9d37ce1105bec6a752009739025522"


def source_video() -> Path:
    value = os.getenv("CLIPKARO_QA_SOURCE_VIDEO", "").strip()
    if not value:
        raise RuntimeError("CLIPKARO_QA_SOURCE_VIDEO is required for this staging-only QA helper.")
    path = Path(value).expanduser()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


async def main() -> None:
    video = source_video()
    mapping = json.loads((D / "bassi-display-word-map.json").read_text(encoding="utf-8"))["words"]
    timeline_path = D / "bassi-native-word-timeline.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    if hashlib.sha256(timeline_path.read_bytes()).hexdigest() != EXPECTED_TIMELINE_SHA256:
        raise RuntimeError("timeline integrity")

    out = D / "exports"
    out.mkdir(exist_ok=True)
    report = []
    for name, center in (("early", .20), ("middle", .50), ("late", .82)):
        start = round(timeline["duration_seconds"] * center - 15, 3)
        end = round(start + 30, 3)
        words = [
            {"text": item["display_word"], "start": item["start"], "end": item["end"]}
            for item in mapping
            if item["end"] >= start and item["start"] <= end and item["display_word"]
        ]
        segments = [{"start": start, "end": end, "text": "", "words": words}]
        srt = out / f"bassi-{name}-display-v1.srt"
        mp4 = out / f"bassi-{name}-display-v1.mp4"
        create_srt(segments, start, end, srt)
        await render_short(video, mp4, start, end, srt, "ClipKaro QA", False)
        report.append({
            "clip_id": name,
            "source_start": start,
            "source_end": end,
            "words_included": len(words),
            "srt": str(srt),
            "output_path": str(mp4),
            "file_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
            "file_size": mp4.stat().st_size,
        })
    (D / "bassi-end-to-end-export-qa.json").write_text(
        json.dumps({"clips": report}, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"exports": len(report), "output": str(out)}))


if __name__ == "__main__":
    asyncio.run(main())

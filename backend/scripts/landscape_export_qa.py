#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.landscape_export_qa import (  # noqa: E402
    FaceBox,
    FaceObservation,
    best_static_focus,
    score_dynamic_focus,
    score_focus,
    summarize_landscape_cases,
)
from app.services.landscape_qualification import (  # noqa: E402
    CASE_COUNT,
    CLIP_SECONDS,
    CONTRACT_VERSION,
    DETECTION_MIN_COVERAGE,
    DETECTION_MIN_OBSERVATIONS,
    EXPORTS_REQUIRED,
    MIN_RELIABLY_SCORED_CASES,
    OUTPUT_AUDIO_CODEC,
    OUTPUT_DURATION_SLACK_SECONDS,
    OUTPUT_MIN_SIZE_BYTES,
    OUTPUT_RESOLUTIONS,
    OUTPUT_VIDEO_CODEC,
    POLICIES,
    SAMPLES_PER_CASE,
    SOURCE_SPECS,
    SOURCE_WINDOW_FRACTIONS,
    TARGET_ASPECT_RATIO,
    threshold_contract_sha256,
)
from app.services.rendering import render_short  # noqa: E402
from app.services.video import find_media_tool  # noqa: E402


# The real source corpus is part of the same source-controlled threshold lock as
# the framing thresholds. Changing a filename/page changes the qualification hash.
PUBLIC_SOURCES: tuple[dict[str, str], ...] = SOURCE_SPECS


def _media_tool(name: str) -> str:
    tool = find_media_tool(name)
    if not tool:
        raise RuntimeError(f"{name} is required for landscape export QA.")
    return tool


def _run(command: list[str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout)[-1200:])
    return proc


def _probe(path: Path) -> dict[str, Any]:
    ffprobe = _media_tool("ffprobe")
    proc = _run([
        ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path),
    ], timeout=60)
    payload = json.loads(proc.stdout)
    video = next((row for row in payload.get("streams", []) if row.get("codec_type") == "video"), {})
    audio = next((row for row in payload.get("streams", []) if row.get("codec_type") == "audio"), {})
    duration = float(payload.get("format", {}).get("duration") or video.get("duration") or 0)
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "video_codec": str(video.get("codec_name") or ""),
        "audio_codec": str(audio.get("codec_name") or ""),
        "duration": round(duration, 3),
        "size_bytes": path.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _acquire_source(source: dict[str, str], target: Path, source_dir: Path | None) -> dict[str, Any]:
    """Use an operator-supplied real-media cache or download the locked public source."""
    if source_dir is not None:
        local = source_dir / source["filename"]
        if not local.is_file():
            raise RuntimeError(
                f"Local landscape source is missing: {local}. "
                "Provide all five locked interview files or omit --source-dir."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if local.resolve() != target.resolve():
            shutil.copy2(local, target)
        if target.stat().st_size < 100_000:
            raise RuntimeError(f"Local interview fixture is unexpectedly small: {local}")
        return {
            **source,
            "acquisition": "operator-supplied-real-media-cache",
            "sha256": _sha256(target),
            "size_bytes": target.stat().st_size,
        }
    evidence = _download(source, target)
    evidence["acquisition"] = "runtime-wikimedia-download"
    return evidence


def _download(source: dict[str, str], target: Path) -> dict[str, Any]:
    encoded = quote(source["filename"], safe="._-()")
    url = f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{encoded}"
    headers = {"User-Agent": "ClipKaroAI-Landscape-QA/1.0 (https://clipkaro.pro)"}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with requests.get(url, stream=True, timeout=(20, 120), headers=headers) as response:
                response.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            if target.stat().st_size < 100_000:
                raise RuntimeError("Downloaded interview fixture is unexpectedly small.")
            return {
                **source,
                "download_url": url,
                "sha256": _sha256(target),
                "size_bytes": target.stat().st_size,
            }
        except Exception as exc:  # pragma: no cover - network-only path
            last_error = exc
            if target.exists():
                target.unlink()
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not download {source['filename']}: {last_error}")


def _extract_landscape_case(source: Path, target: Path, start: float, seconds: float) -> None:
    ffmpeg = _media_tool("ffmpeg")
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg, "-nostdin", "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{seconds:.3f}",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(target),
    ], timeout=300)
    metadata = _probe(target)
    if metadata["width"] != 1280 or metadata["height"] != 720 or metadata["duration"] < seconds - 1.0:
        raise RuntimeError(f"Landscape case normalization failed: {metadata}")


def _dedupe_faces(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda row: row[2] * row[3], reverse=True):
        x, y, w, h = box
        center = (x + w / 2, y + h / 2)
        if any(abs(center[0] - (kx + kw / 2)) < min(w, kw) * .35 and
               abs(center[1] - (ky + kh / 2)) < min(h, kh) * .35
               for kx, ky, kw, kh in kept):
            continue
        kept.append(box)
    return kept


def _detect_faces(path: Path, sample_count: int) -> tuple[list[FaceObservation], dict[str, Any]]:
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - heavyweight workflow dependency
        raise RuntimeError("Install opencv-python-headless to run real landscape face QA.") from exc

    frontal = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    if frontal.empty() or profile.empty():
        raise RuntimeError("OpenCV face cascades are unavailable.")

    metadata = _probe(path)
    duration = metadata["duration"]
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open {path}.")
    observations: list[FaceObservation] = []
    requested = max(6, int(sample_count))
    sample_times = [
        max(0.15, min(duration - 0.15, (index + .5) * duration / requested))
        for index in range(requested)
    ]
    multi_face = 0
    all_face_counts: list[int] = []
    try:
        for timestamp in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
            if not ok or frame is None:
                all_face_counts.append(0)
                continue
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            min_side = max(38, int(min(width, height) * .075))
            front_boxes = list(frontal.detectMultiScale(
                gray, scaleFactor=1.08, minNeighbors=5, minSize=(min_side, min_side),
            ))
            boxes = [tuple(map(int, row)) for row in front_boxes]
            if not boxes:
                profile_boxes = list(profile.detectMultiScale(
                    gray, scaleFactor=1.08, minNeighbors=4, minSize=(min_side, min_side),
                ))
                flipped = cv2.flip(gray, 1)
                flipped_boxes = list(profile.detectMultiScale(
                    flipped, scaleFactor=1.08, minNeighbors=4, minSize=(min_side, min_side),
                ))
                boxes.extend(tuple(map(int, row)) for row in profile_boxes)
                boxes.extend((width - int(x) - int(w), int(y), int(w), int(h)) for x, y, w, h in flipped_boxes)
            boxes = _dedupe_faces(boxes)
            all_face_counts.append(len(boxes))
            if not boxes:
                continue
            if len(boxes) >= 2:
                multi_face += 1
            primary = max(boxes, key=lambda row: row[2] * row[3])
            observations.append(FaceObservation(
                time=float(timestamp),
                frame_width=float(width),
                frame_height=float(height),
                primary=FaceBox(x=primary[0], y=primary[1], width=primary[2], height=primary[3]),
                face_count=len(boxes),
            ))
    finally:
        cap.release()
    return observations, {
        "requested_samples": requested,
        "detected_samples": len(observations),
        "detection_coverage": round(len(observations) / requested, 4),
        "multi_face_samples": multi_face,
        "face_counts": all_face_counts,
    }


async def _render_policy(source: Path, output: Path, duration: float, resolution: str,
                         *, focus_x: float, keyframes: list[dict[str, float]] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await render_short(
            source=source,
            output=output,
            start=0,
            end=duration,
            srt=None,
            hook="",
            watermark=False,
            resolution=resolution,
            aspect_ratio=TARGET_ASPECT_RATIO,
            caption_style="minimal",
            brand_text="ClipKaro AI",
            primary_color="#DFFF57",
            focus_x=focus_x,
            caption_position="bottom",
            crop_keyframes=keyframes,
            source_caption_band=None,
        )
        metadata = _probe(output)
        expected = OUTPUT_RESOLUTIONS[resolution]
        valid = (
            metadata["width"] == expected[0]
            and metadata["height"] == expected[1]
            and metadata["video_codec"] == OUTPUT_VIDEO_CODEC
            and metadata["audio_codec"] == OUTPUT_AUDIO_CODEC
            and metadata["duration"] >= duration - OUTPUT_DURATION_SLACK_SECONDS
            and metadata["size_bytes"] > OUTPUT_MIN_SIZE_BYTES
        )
        return {
            "ok": valid,
            "render_seconds": round(time.perf_counter() - started, 3),
            "sha256": _sha256(output) if output.exists() else None,
            **metadata,
            "error": None if valid else "output_validation_failed",
        }
    except Exception as exc:  # pragma: no cover - heavyweight workflow evidence
        return {
            "ok": False,
            "render_seconds": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}"[:600],
        }


def _focus_span(observations: list[FaceObservation]) -> float:
    if len(observations) < 2:
        return 0.0
    from app.services.landscape_export_qa import desired_focus_for_face
    rows = [desired_focus_for_face(row) for row in observations]
    return round(max(rows) - min(rows), 3)


def _summary_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Landscape Export QA",
        "",
        f"**Verdict:** `{summary['verdict']}`",
        "",
        f"- Actual exports: **{report['export_count']}**",
        f"- Validated exports: **{report['successful_export_count']}**",
        f"- Reliably face-scored cases: **{summary.get('scored_cases', 0)} / {len(report['cases'])}**",
        f"- Default-center case pass rate: **{summary.get('default_case_pass_rate', 0):.0%}**",
        f"- Best single manual-focus pass rate: **{summary.get('manual_case_pass_rate', 0):.0%}**",
        f"- Time-varying focus pass rate: **{summary.get('dynamic_case_pass_rate', 0):.0%}**",
        f"- Dynamic-only rescue rate: **{summary.get('dynamic_only_rescue_rate', 0):.0%}**",
        f"- Multi-face sampled-frame rate: **{summary.get('multi_face_sample_rate', 0):.0%}**",
        "",
        "| Case | Detection | Focus span | Center | Manual | Dynamic |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['id']} | {case['detection']['detection_coverage']:.0%} | "
            f"{case['focus_span']:.1f} pts | "
            f"{'PASS' if case['default']['passed'] else 'FAIL'} | "
            f"{'PASS' if case['manual']['passed'] else 'FAIL'} | "
            f"{'PASS' if case['dynamic']['passed'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "`manual` is the best single focus_x a creator could choose for the entire clip. ",
        "`dynamic` uses time-varying primary-face observations as an oracle for what automatic tracking could recover. ",
        "Largest detected face is a framing proxy, not active-speaker diarization; multi-face clips are flagged separately.",
    ])
    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    if args.cases != CASE_COUNT:
        raise SystemExit(
            f"The locked launch contract is {CASE_COUNT} real clips x {len(POLICIES)} policies = {EXPORTS_REQUIRED} exports."
        )
    if float(args.clip_seconds) != CLIP_SECONDS:
        raise SystemExit(
            f"clip-seconds is threshold-locked at {CLIP_SECONDS:g}; do not tune it after seeing results."
        )
    if int(args.samples) != SAMPLES_PER_CASE:
        raise SystemExit(
            f"samples is threshold-locked at {SAMPLES_PER_CASE}; do not tune it after seeing results."
        )

    started_at = datetime.now(timezone.utc).isoformat()
    output_root = Path(args.output_dir).resolve()
    downloads = output_root / "downloads"
    cases_dir = output_root / "cases"
    exports_dir = output_root / "exports"
    for path in (downloads, cases_dir, exports_dir):
        path.mkdir(parents=True, exist_ok=True)
    source_dir = Path(args.source_dir).resolve() if args.source_dir else None

    source_evidence: list[dict[str, Any]] = []
    normalized_cases: list[dict[str, Any]] = []
    case_number = 0
    for source in PUBLIC_SOURCES:
        source_path = downloads / source["filename"]
        evidence = _acquire_source(source, source_path, source_dir)
        source_metadata = _probe(source_path)
        evidence["media"] = source_metadata
        source_evidence.append(evidence)
        duration = source_metadata["duration"]
        latest = max(0.0, duration - args.clip_seconds - 0.25)
        starts = [min(latest, duration * fraction) for fraction in SOURCE_WINDOW_FRACTIONS]
        for window_index, start in enumerate(starts, 1):
            case_number += 1
            case_id = f"{source['id']}-{window_index}"
            case_path = cases_dir / f"{case_id}.mp4"
            _extract_landscape_case(source_path, case_path, start, args.clip_seconds)
            normalized_cases.append({
                "id": case_id,
                "source_id": source["id"],
                "source_page": source["source_page"],
                "source_sha256": evidence["sha256"],
                "start_seconds": round(start, 3),
                "case_sha256": _sha256(case_path),
                "path": case_path,
            })
    if len(normalized_cases) != args.cases:
        raise RuntimeError(f"Built {len(normalized_cases)} cases instead of {args.cases}.")

    case_reports: list[dict[str, Any]] = []
    export_records: list[dict[str, Any]] = []
    for index, case in enumerate(normalized_cases):
        observations, detection = _detect_faces(case["path"], args.samples)
        scored = (
            detection["detection_coverage"] >= DETECTION_MIN_COVERAGE
            and len(observations) >= DETECTION_MIN_OBSERVATIONS
        )
        default_score = score_focus(observations, lambda _: 50)
        manual_focus, manual_score = best_static_focus(observations)
        keyframes, dynamic_score = score_dynamic_focus(observations, args.clip_seconds)
        resolution = "1080p" if index % 3 == 2 else "720p"
        policies = (
            ("center", 50.0, None),
            ("manual", manual_focus, None),
            ("dynamic", manual_focus, keyframes if scored else None),
        )
        rendered: dict[str, Any] = {}
        for policy, focus, policy_keyframes in policies:
            target = exports_dir / f"{case['id']}-{policy}-{resolution}.mp4"
            result = await _render_policy(
                case["path"], target, args.clip_seconds, resolution,
                focus_x=focus, keyframes=policy_keyframes,
            )
            record = {
                "case_id": case["id"],
                "policy": policy,
                "resolution": resolution,
                "focus_x": round(focus, 3),
                "keyframe_count": len(policy_keyframes or []),
                "path": target.relative_to(output_root).as_posix(),
                **result,
            }
            export_records.append(record)
            rendered[policy] = record
        case_reports.append({
            "id": case["id"],
            "source_id": case["source_id"],
            "source_page": case["source_page"],
            "source_sha256": case["source_sha256"],
            "source_window_start": case["start_seconds"],
            "case_sha256": case["case_sha256"],
            "scored": scored,
            "sample_count": len(observations),
            "multi_face_samples": detection["multi_face_samples"],
            "detection": detection,
            "focus_span": _focus_span(observations),
            "manual_focus_x": round(manual_focus, 3),
            "dynamic_keyframes": keyframes,
            "default": default_score.as_dict(),
            "manual": manual_score.as_dict(),
            "dynamic": dynamic_score.as_dict(),
            "exports": rendered,
        })

    summary = summarize_landscape_cases(case_reports)
    successful_exports = sum(bool(row.get("ok")) for row in export_records)
    report = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at,
        "tested_sha": os.environ.get("TESTED_SHA"),
        "threshold_lock": {
            "contract_version": CONTRACT_VERSION,
            "threshold_sha256": threshold_contract_sha256(),
        },
        "purpose": "Determine whether a single manual horizontal focus is sufficient for landscape podcast Shorts or automatic face tracking is a launch-critical need.",
        "source_policy": "Runtime-downloaded Creative-Commons interviews from Wikimedia Commons; source pages remain the attribution/license authority.",
        "case_count": len(case_reports),
        "policies_per_case": 3,
        "export_count": len(export_records),
        "successful_export_count": successful_exports,
        "failed_export_count": len(export_records) - successful_exports,
        "clip_seconds": args.clip_seconds,
        "target_aspect_ratio": TARGET_ASPECT_RATIO,
        "primary_face_rule": "largest detected face per sampled frame; framing proxy only, not active-speaker diarization",
        "sources": source_evidence,
        "cases": case_reports,
        "exports": export_records,
        "summary": summary,
    }
    report_path = output_root / "landscape-export-qa-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "landscape-export-qa-summary.md").write_text(_summary_markdown(report), encoding="utf-8")

    print(json.dumps({
        "verdict": summary["verdict"],
        "manual_focus_sufficient_for_now": summary["manual_focus_sufficient_for_now"],
        "export_count": len(export_records),
        "successful_export_count": successful_exports,
        "scored_cases": summary.get("scored_cases", 0),
        "manual_case_pass_rate": summary.get("manual_case_pass_rate"),
        "dynamic_only_rescue_rate": summary.get("dynamic_only_rescue_rate"),
        "speaker_tracking_followup_recommended": summary.get("speaker_tracking_followup_recommended"),
    }, indent=2))

    complete = (
        len(export_records) == EXPORTS_REQUIRED
        and successful_exports == EXPORTS_REQUIRED
        and int(summary.get("scored_cases", 0)) >= MIN_RELIABLY_SCORED_CASES
        and bool(summary.get("evidence_valid"))
    )
    if not complete:
        print(f"Landscape QA is incomplete or invalid; inspect {report_path}.", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 30 real ClipKaro exports against landscape interview footage.")
    parser.add_argument("--output-dir", default="landscape_qa")
    parser.add_argument("--cases", type=int, default=CASE_COUNT)
    parser.add_argument("--clip-seconds", type=float, default=CLIP_SECONDS)
    parser.add_argument("--samples", type=int, default=SAMPLES_PER_CASE)
    parser.add_argument(
        "--source-dir",
        default="",
        help="Optional directory containing the five locked real Wikimedia interview files; avoids network downloads.",
    )
    args = parser.parse_args()
    os.environ.setdefault("MEDIA_FFMPEG_THREADS", "2")
    os.environ.setdefault("MEDIA_PROCESS_TIMEOUT_SECONDS", "300")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import math
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from app.services.video import find_media_tool


MIN_LANGUAGE_MATCH_RATE = 0.80
MIN_TIMESTAMP_VALID_RATE = 0.95


_TOKEN_RE = re.compile(r"[\w\u0900-\u097f]+", re.UNICODE)


@dataclass(frozen=True)
class StressScenario:
    name: str
    description: str
    max_p90_wer: float
    max_p90_cer: float
    max_p95_rtf: float
    min_success_rate: float = 0.80
    requires_street_noise: bool = False


# These are launch gates, not research-paper targets. They intentionally allow
# some degradation while refusing cases where creators would have to rewrite a
# large part of the transcript. Keep thresholds versioned in source control so
# a future model change cannot silently lower the quality bar.
STRESS_SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario("clean", "clean corpus baseline", 0.28, 0.18, 1.50, 0.95),
    StressScenario("fast_125", "25% faster speech", 0.38, 0.24, 1.50),
    StressScenario("fast_145", "45% faster speech", 0.48, 0.30, 1.50),
    StressScenario("background_noise", "moderate synthetic broadband background noise", 0.45, 0.28, 1.70),
    StressScenario("street_noise", "real street/traffic noise mixed over speech", 0.50, 0.32, 1.80, requires_street_noise=True),
    StressScenario("phone_band", "8 kHz telephone-band speech", 0.45, 0.28, 1.60),
    StressScenario("low_bitrate", "24 kbps AAC compression", 0.42, 0.27, 1.60),
    StressScenario("clipped", "hard-clipped/overdriven speech", 0.50, 0.32, 1.70),
    StressScenario("dropouts", "short packet-loss style mute gaps", 0.52, 0.34, 1.70),
    StressScenario("room_echo", "moderate short-room echo", 0.48, 0.31, 1.70),
)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(_TOKEN_RE.findall(normalized))


def _levenshtein(reference: list[str], hypothesis: list[str]) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, ref_item in enumerate(reference, start=1):
        current = [row]
        for col, hyp_item in enumerate(hypothesis, start=1):
            current.append(min(
                current[-1] + 1,
                previous[col] + 1,
                previous[col - 1] + (ref_item != hyp_item),
            ))
        previous = current
    return previous[-1]


def error_rate(reference: str, hypothesis: str, *, unit: str = "word") -> float:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if unit == "word":
        ref_items = ref.split()
        hyp_items = hyp.split()
    elif unit == "char":
        ref_items = list(ref.replace(" ", ""))
        hyp_items = list(hyp.replace(" ", ""))
    else:
        raise ValueError("unit must be 'word' or 'char'")
    if not ref_items:
        return 0.0 if not hyp_items else 1.0
    return _levenshtein(ref_items, hyp_items) / len(ref_items)


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return math.inf
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def language_family(language: str) -> str:
    value = (language or "").strip().lower()
    if value in {"hinglish", "hi-en", "en-hi"}:
        return "hinglish"
    if value in {"hi", "hindi"}:
        return "hi"
    if value in {"mr", "marathi"}:
        return "mr"
    return value


def expected_language_matches(expected: str, detected: str) -> bool:
    expected = (expected or "auto").strip().lower()
    detected = (detected or "").strip().lower()
    if expected in {"hinglish", "hi-en", "en-hi"}:
        return detected in {"hi", "en", "ur"}
    if expected == "hindi":
        expected = "hi"
    if expected == "marathi":
        expected = "mr"
    if expected in {"", "auto"}:
        return bool(detected)
    return detected == expected


def validate_timestamps(segments: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    issues: list[str] = []
    previous_segment_start = -1.0
    word_count = 0
    for index, segment in enumerate(segments):
        start = float(segment.get("start", 0))
        end = float(segment.get("end", 0))
        if start < -0.02 or end <= start:
            issues.append(f"segment_{index}_invalid_range")
        if start + 0.05 < previous_segment_start:
            issues.append(f"segment_{index}_out_of_order")
        if end > duration + 0.75:
            issues.append(f"segment_{index}_past_media_end")
        previous_segment_start = start
        previous_word_start = start - 0.05
        for word_index, word in enumerate(segment.get("words") or []):
            word_count += 1
            word_start = float(word.get("start", 0))
            word_end = float(word.get("end", 0))
            if word_end <= word_start:
                issues.append(f"segment_{index}_word_{word_index}_collapsed")
            if word_start + 0.05 < previous_word_start:
                issues.append(f"segment_{index}_word_{word_index}_out_of_order")
            if word_start < start - 0.35 or word_end > end + 0.35:
                issues.append(f"segment_{index}_word_{word_index}_outside_segment")
            previous_word_start = word_start
    return {"valid": not issues, "issues": issues[:30], "word_count": word_count}


def transcript_text(segments: list[dict[str, Any]]) -> str:
    return " ".join(str(segment.get("text") or "").strip() for segment in segments if str(segment.get("text") or "").strip())


def probe_duration(path: Path) -> float:
    ffprobe = find_media_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe is required for ASR stress testing.")
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Could not probe benchmark media: {proc.stderr[-400:]}")
    try:
        duration = float(proc.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("Benchmark media has no readable duration.") from exc
    if duration <= 0:
        raise RuntimeError("Benchmark media duration must be positive.")
    return duration


def _encode_command(source: Path, output: Path, scenario: str, street_noise: Path | None) -> list[str]:
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for ASR stress testing.")
    base = [ffmpeg, "-nostdin", "-y", "-i", str(source)]
    mono = "aresample=16000,pan=mono|c0=c0"
    if scenario == "clean":
        return base + ["-vn", "-af", mono, "-c:a", "aac", "-b:a", "96k", str(output)]
    if scenario == "fast_125":
        return base + ["-vn", "-af", f"{mono},atempo=1.25", "-c:a", "aac", "-b:a", "96k", str(output)]
    if scenario == "fast_145":
        return base + ["-vn", "-af", f"{mono},atempo=1.45", "-c:a", "aac", "-b:a", "96k", str(output)]
    if scenario == "phone_band":
        return base + ["-vn", "-af", f"{mono},highpass=f=300,lowpass=f=3400,aresample=8000,aresample=16000", "-c:a", "aac", "-b:a", "48k", str(output)]
    if scenario == "low_bitrate":
        return base + ["-vn", "-af", mono, "-c:a", "aac", "-b:a", "24k", str(output)]
    if scenario == "clipped":
        return base + ["-vn", "-af", f"{mono},volume=10dB,asoftclip=type=hard:threshold=0.35", "-c:a", "aac", "-b:a", "64k", str(output)]
    if scenario == "dropouts":
        dropout = "volume=0:enable='between(t,7.0,7.28)+between(t,16.0,16.38)+between(t,25.0,25.22)'"
        return base + ["-vn", "-af", f"{mono},{dropout}", "-c:a", "aac", "-b:a", "64k", str(output)]
    if scenario == "room_echo":
        return base + ["-vn", "-af", f"{mono},aecho=0.8:0.55:65:0.28", "-c:a", "aac", "-b:a", "64k", str(output)]
    if scenario == "background_noise":
        duration = probe_duration(source)
        return base + [
            "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.11:r=16000:seed=9001",
            "-filter_complex",
            f"[0:a]{mono}[speech];[1:a]atrim=duration={duration:.3f},volume=0.38[noise];[speech][noise]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[out]",
            "-map", "[out]", "-c:a", "aac", "-b:a", "64k", str(output),
        ]
    if scenario == "street_noise":
        if not street_noise or not street_noise.exists():
            raise RuntimeError("street_noise scenario requires a real street-noise recording.")
        return base + [
            "-stream_loop", "-1", "-i", str(street_noise),
            "-filter_complex",
            f"[0:a]{mono}[speech];[1:a]{mono},volume=0.55[street];[speech][street]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[out]",
            "-map", "[out]", "-c:a", "aac", "-b:a", "64k", str(output),
        ]
    raise ValueError(f"Unknown ASR stress scenario: {scenario}")


def create_stress_variant(source: Path, output: Path, scenario: str, *, street_noise: Path | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = _encode_command(source, output, scenario, street_noise)
    proc = subprocess.run(command, capture_output=True, timeout=180, check=False)
    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        detail = proc.stderr.decode(errors="ignore")[-800:]
        raise RuntimeError(f"FFmpeg could not create {scenario} stress audio: {detail}")
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"FFmpeg produced an invalid {scenario} stress fixture.")
    return output


def _summarize_rows(rows: list[dict[str, Any]], scenario: StressScenario) -> dict[str, Any]:
    if not rows:
        return {"passed": False, "reason": "no_results", "cases": 0}
    successful = [row for row in rows if not row.get("error")]
    success_rate = len(successful) / len(rows)
    wers = [float(row["wer"]) for row in successful]
    cers = [float(row["cer"]) for row in successful]
    rtfs = [float(row["rtf"]) for row in successful]
    language_rate = mean(float(bool(row.get("language_match"))) for row in successful) if successful else 0.0
    timestamp_rate = mean(float(bool(row.get("timestamps_valid"))) for row in successful) if successful else 0.0
    p90_wer = percentile(wers, 0.90)
    p90_cer = percentile(cers, 0.90)
    p95_rtf = percentile(rtfs, 0.95)
    passed = bool(successful) and all((
        success_rate >= scenario.min_success_rate,
        p90_wer <= scenario.max_p90_wer,
        p90_cer <= scenario.max_p90_cer,
        p95_rtf <= scenario.max_p95_rtf,
        language_rate >= MIN_LANGUAGE_MATCH_RATE,
        timestamp_rate >= MIN_TIMESTAMP_VALID_RATE,
    ))
    return {
        "passed": passed,
        "cases": len(rows),
        "successful_cases": len(successful),
        "success_rate": round(success_rate, 4),
        "p90_wer": round(p90_wer, 4),
        "p90_cer": round(p90_cer, 4),
        "p95_rtf": round(p95_rtf, 4),
        "worst_wer": round(max(wers), 4) if wers else math.inf,
        "worst_cer": round(max(cers), 4) if cers else math.inf,
        "language_match_rate": round(language_rate, 4),
        "timestamp_valid_rate": round(timestamp_rate, 4),
        "limits": {
            "min_success_rate": scenario.min_success_rate,
            "max_p90_wer": scenario.max_p90_wer,
            "max_p90_cer": scenario.max_p90_cer,
            "max_p95_rtf": scenario.max_p95_rtf,
            "min_language_match_rate": MIN_LANGUAGE_MATCH_RATE,
            "min_timestamp_valid_rate": MIN_TIMESTAMP_VALID_RATE,
        },
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    scenario_summaries: dict[str, dict[str, Any]] = {}
    overall_pass = True
    for scenario in STRESS_SCENARIOS:
        rows = [row for row in results if row.get("scenario") == scenario.name]
        if not rows:
            scenario_summaries[scenario.name] = {"passed": False, "reason": "no_results"}
            overall_pass = False
            continue

        aggregate = _summarize_rows(rows, scenario)
        families = sorted({language_family(str(row.get("language") or "")) for row in rows if row.get("language")})
        by_language: dict[str, dict[str, Any]] = {}
        for family in families:
            family_rows = [row for row in rows if language_family(str(row.get("language") or "")) == family]
            by_language[family] = _summarize_rows(family_rows, scenario)

        family_pass = bool(by_language) and all(details.get("passed", False) for details in by_language.values())
        passed = bool(aggregate.get("passed")) and family_pass
        overall_pass = overall_pass and passed
        scenario_summaries[scenario.name] = {
            **aggregate,
            "aggregate_passed": bool(aggregate.get("passed")),
            "by_language": by_language,
            "passed": passed,
        }
    return {"passed": overall_pass, "scenarios": scenario_summaries}

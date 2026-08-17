#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

# Run from backend/ so app imports resolve the same way as production/tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.asr_benchmark import (  # noqa: E402
    STRESS_SCENARIOS,
    create_stress_variant,
    error_rate,
    expected_language_matches,
    language_family,
    probe_duration,
    summarize_results,
    transcript_text,
    validate_timestamps,
)
from app.services.asr_negative_controls import NEGATIVE_CONTROLS, create_negative_control  # noqa: E402
from app.services.asr_qualification import QUALIFICATION_CONTRACT_VERSION, threshold_contract_sha256  # noqa: E402
from app.services.transcription import transcribe  # noqa: E402


REQUIRED_LANGUAGE_FAMILIES = {"hi", "mr", "hinglish"}
_SAFE_NONSPEECH_REJECTIONS = (
    "No clear speech was detected",
    "Transcript quality verification failed",
    "Transcript needs review:",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> tuple[list[dict[str, Any]], Path | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        cases = payload
        street_noise = None
    elif isinstance(payload, dict):
        cases = payload.get("cases") or []
        street_value = str(payload.get("street_noise") or "").strip()
        street_noise = (path.parent / street_value).resolve() if street_value else None
    else:
        raise ValueError("Benchmark manifest must be a JSON list or object with a cases array.")
    if not cases:
        raise ValueError("Benchmark manifest has no cases.")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(cases):
        if not isinstance(raw, dict):
            raise ValueError(f"Case {index} is not an object.")
        rel = str(raw.get("path") or "").strip()
        reference = str(raw.get("reference") or "").strip()
        language = str(raw.get("language") or "").strip().lower()
        case_id = str(raw.get("id") or f"case-{index + 1}").strip()
        if not rel or not reference or not language:
            raise ValueError(f"Case {index} requires path, reference and language.")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate benchmark case id: {case_id}")
        seen_ids.add(case_id)
        media = (path.parent / rel).resolve()
        if not media.exists():
            raise FileNotFoundError(f"Benchmark media does not exist: {media}")
        actual_hash = _sha256(media)
        declared_hash = str(raw.get("sha256") or "").strip().lower()
        if declared_hash and declared_hash != actual_hash:
            raise RuntimeError(f"Benchmark media hash mismatch for {case_id}.")
        normalized.append({
            **raw,
            "id": case_id,
            "media": media,
            "sha256": actual_hash,
            "reference": reference,
            "language": language,
            "language_hint": str(raw.get("language_hint") or "auto").strip().lower(),
        })
    return normalized, street_noise


def _coverage(cases: list[dict[str, Any]], min_cases: int) -> dict[str, Any]:
    counts = Counter(language_family(str(case["language"])) for case in cases)
    missing = sorted(language for language in REQUIRED_LANGUAGE_FAMILIES if counts[language] < min_cases)
    return {
        "passed": not missing,
        "required": sorted(REQUIRED_LANGUAGE_FAMILIES),
        "min_cases_per_language": min_cases,
        "counts": dict(sorted(counts.items())),
        "missing_or_underrepresented": missing,
    }


async def _run_case(
    case: dict[str, Any],
    scenario: str,
    model: str,
    workdir: Path,
    street_noise: Path | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": case["id"],
        "source": str(case.get("source") or "curated"),
        "source_sha256": case["sha256"],
        "language": case["language"],
        "language_family": language_family(str(case["language"])),
        "language_hint": case["language_hint"],
        "scenario": scenario,
    }
    source = Path(case["media"])
    variant = workdir / f"{case['id']}-{scenario}.m4a"
    try:
        create_stress_variant(source, variant, scenario, street_noise=street_noise)
        duration = probe_duration(variant)
        started = time.perf_counter()
        detected, segments = await transcribe(variant, model_name=model, language_hint=case["language_hint"])
        elapsed = time.perf_counter() - started
        hypothesis = transcript_text(segments)
        timestamp_check = validate_timestamps(segments, duration)
        result.update({
            "detected_language": detected,
            "language_match": expected_language_matches(case["language"], detected),
            "duration_seconds": round(duration, 3),
            "elapsed_seconds": round(elapsed, 3),
            "rtf": round(elapsed / max(duration, 0.001), 4),
            "wer": round(error_rate(case["reference"], hypothesis, unit="word"), 4),
            "cer": round(error_rate(case["reference"], hypothesis, unit="char"), 4),
            "timestamps_valid": bool(timestamp_check["valid"]),
            "timestamp_issues": timestamp_check["issues"],
            "word_timestamps": timestamp_check["word_count"],
            "reference": case["reference"],
            "hypothesis": hypothesis,
        })
    except Exception as exc:  # benchmark must report rejection/crash as a result
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        variant.unlink(missing_ok=True)
        variant.with_suffix(".wav").unlink(missing_ok=True)
    return result


async def _run_negative_control(kind: str, model: str, workdir: Path) -> dict[str, Any]:
    media = workdir / f"negative-{kind}.m4a"
    result: dict[str, Any] = {"kind": kind, "passed": False}
    try:
        create_negative_control(media, kind, seconds=30.0)
        detected, segments = await transcribe(media, model_name=model, language_hint="auto")
        result.update({
            "reason": "hallucinated_transcript",
            "detected_language": detected,
            "hypothesis": transcript_text(segments),
        })
    except RuntimeError as exc:
        message = str(exc)
        safe_rejection = any(marker in message for marker in _SAFE_NONSPEECH_REJECTIONS)
        result.update({
            "passed": safe_rejection,
            "reason": "safe_rejection" if safe_rejection else "unexpected_runtime_failure",
            "rejection": message,
        })
    except Exception as exc:
        result.update({"reason": "unexpected_exception", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        media.unlink(missing_ok=True)
        media.with_suffix(".wav").unlink(missing_ok=True)
    return result


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "qualification" and args.min_cases_per_language < 2:
        raise RuntimeError("Qualification requires at least 2 cases per Hindi, Marathi and Hinglish family.")

    manifest = Path(args.manifest).resolve()
    cases, manifest_street_noise = _load_manifest(manifest)
    street_noise = Path(args.street_noise).resolve() if args.street_noise else manifest_street_noise
    scenarios = [item.name for item in STRESS_SCENARIOS] if args.scenarios == "all" else [
        item.strip() for item in args.scenarios.split(",") if item.strip()
    ]
    known = {item.name for item in STRESS_SCENARIOS}
    unknown = sorted(set(scenarios) - known)
    if unknown:
        raise ValueError(f"Unknown scenarios: {', '.join(unknown)}")

    coverage = _coverage(cases, args.min_cases_per_language)
    if args.mode == "qualification" and not coverage["passed"]:
        raise RuntimeError(
            "Qualification corpus is incomplete: " + ", ".join(coverage["missing_or_underrepresented"])
        )
    if args.mode == "qualification":
        hinted_cases = [case["id"] for case in cases if case["language_hint"] not in {"", "auto"}]
        if hinted_cases:
            raise RuntimeError(
                "Qualification must exercise the default auto-language path. Forced hints found on: "
                + ", ".join(hinted_cases)
            )
    if args.mode == "qualification" and set(scenarios) != known:
        missing_scenarios = sorted(known - set(scenarios))
        raise RuntimeError(
            "Qualification must run every mandatory stress scenario. Missing: " + ", ".join(missing_scenarios)
        )
    if args.mode == "qualification" and "street_noise" in scenarios and (not street_noise or not street_noise.exists()):
        raise RuntimeError(
            "Qualification requires a real street-noise recording. Pass --street-noise or set street_noise in the manifest."
        )

    settings = get_settings()
    if args.asr_mode:
        settings.asr_mode = args.asr_mode
    if settings.asr_mode == "local" and settings.transcription_backend != "faster-whisper":
        raise RuntimeError(
            "Local acoustic qualification requires TRANSCRIPTION_BACKEND=faster-whisper; fixture mode cannot qualify production ASR."
        )

    results: list[dict[str, Any]] = []
    negative_controls: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="clipkaro-asr-stress-") as temp:
        workdir = Path(temp)
        for case in cases:
            for scenario in scenarios:
                print(f"[ASR] {case['id']} / {case['language']} / hint={case['language_hint']} / {scenario}", flush=True)
                result = await _run_case(case, scenario, args.model, workdir, street_noise)
                results.append(result)
                if result.get("error"):
                    print(f"      rejected: {result['error']}", flush=True)
                else:
                    print(
                        f"      WER={result['wer']:.3f} CER={result['cer']:.3f} "
                        f"RTF={result['rtf']:.2f} lang={result['detected_language']}",
                        flush=True,
                    )
        if args.mode == "qualification":
            for kind in NEGATIVE_CONTROLS:
                print(f"[ASR negative] {kind}", flush=True)
                control = await _run_negative_control(kind, args.model, workdir)
                negative_controls.append(control)
                print(
                    "      safe rejection" if control["passed"] else f"      FAILED: {control.get('reason')}",
                    flush=True,
                )

    summary = summarize_results(results)
    selected = set(scenarios)
    selected_scenarios_passed = all(
        details.get("passed", False)
        for name, details in summary["scenarios"].items()
        if name in selected
    )
    if args.mode == "smoke":
        negative_pass = True
    else:
        negative_pass = len(negative_controls) == len(NEGATIVE_CONTROLS) and all(
            item.get("passed") for item in negative_controls
        )
    production_ready = (
        args.mode == "qualification"
        and coverage["passed"]
        and selected_scenarios_passed
        and negative_pass
    )
    street_hash = _sha256(street_noise) if street_noise and street_noise.exists() else None
    return {
        "benchmark_version": "2026-08-11-v5",
        "qualification_contract_version": QUALIFICATION_CONTRACT_VERSION,
        "threshold_sha256": threshold_contract_sha256(),
        "mode": args.mode,
        "model": args.model,
        "asr_mode": settings.asr_mode,
        "asr_candidate": {
            "primary_provider": settings.asr_primary_provider if settings.asr_mode == "api" else "local-whisper",
            "primary_model": settings.groq_asr_model if settings.asr_mode == "api" else args.model,
            "fallback_provider": settings.asr_fallback_provider if settings.asr_mode == "api" else None,
            "fallback_model": settings.cloudflare_asr_model if settings.asr_mode == "api" else None,
        },
        "transcription_backend": settings.transcription_backend,
        "require_asr_consensus": settings.require_asr_consensus,
        "secondary_model": settings.whisper_secondary_model,
        "alignment_backend": settings.alignment_backend,
        "qualification_requires_auto_language": True,
        "corpus": coverage,
        "corpus_cases": [
            {
                "id": case["id"],
                "language": case["language"],
                "language_hint": case["language_hint"],
                "source": str(case.get("source") or "curated"),
                "sha256": case["sha256"],
            }
            for case in cases
        ],
        "street_noise_supplied": bool(street_hash),
        "street_noise_sha256": street_hash,
        "scenarios_requested": scenarios,
        "selected_scenarios_passed": selected_scenarios_passed,
        "summary": summary,
        "negative_controls": {
            "required": list(NEGATIVE_CONTROLS),
            "passed": negative_pass,
            "results": negative_controls,
        },
        "production_ready": production_ready,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress-test ClipKaro's real faster-whisper pipeline.")
    parser.add_argument("--manifest", required=True, help="Corpus manifest JSON; paths are relative to the manifest.")
    parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "medium"))
    parser.add_argument("--asr-mode", choices=("api", "local"), default="", help="Candidate mode. API mode is recorded but remains quality-uncertified until this full corpus passes.")
    parser.add_argument("--scenarios", default="all", help="all or comma-separated scenario names")
    parser.add_argument("--street-noise", default="", help="Real street/traffic recording used for the street_noise mix")
    parser.add_argument("--mode", choices=("qualification", "smoke"), default="qualification")
    parser.add_argument("--min-cases-per-language", type=int, default=2)
    parser.add_argument("--output", default="asr-stress-report.json")
    args = parser.parse_args()

    try:
        report = asyncio.run(run(args))
    except Exception as exc:
        print(f"ASR stress benchmark could not run: {exc}", file=sys.stderr)
        return 3

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {output.resolve()}")
    if args.mode == "qualification":
        print("PRODUCTION READY" if report["production_ready"] else "NOT PRODUCTION READY")
        return 0 if report["production_ready"] else 2
    print("SELECTED STRESS SWEEP PASSED" if report["selected_scenarios_passed"] else "SELECTED STRESS SWEEP FAILED")
    return 0 if report["selected_scenarios_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

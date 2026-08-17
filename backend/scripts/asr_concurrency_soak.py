#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.asr_benchmark import language_family, transcript_text  # noqa: E402
from app.services.asr_qualification import QUALIFICATION_CONTRACT_VERSION, threshold_contract_sha256  # noqa: E402
from app.services.asr_gate import asr_queue_overview, asr_queue_snapshot  # noqa: E402
from app.services.transcription import transcribe  # noqa: E402


REQUIRED = ("hi", "mr", "hinglish")


def _load_cases(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise RuntimeError("ASR concurrency manifest has no cases array.")

    selected: dict[str, dict[str, Any]] = {}
    for raw in cases:
        if not isinstance(raw, dict):
            continue
        family = language_family(str(raw.get("language") or ""))
        if family not in REQUIRED or family in selected:
            continue
        hint = str(raw.get("language_hint") or "auto").strip().lower()
        if hint not in {"", "auto"}:
            continue
        media = (manifest_path.parent / str(raw.get("path") or "")).resolve()
        if not media.exists():
            raise FileNotFoundError(media)
        selected[family] = {
            "id": str(raw.get("id") or family),
            "family": family,
            "language": str(raw.get("language") or family),
            "language_hint": "auto",
            "media": media,
        }

    missing = [family for family in REQUIRED if family not in selected]
    if missing:
        raise RuntimeError("Concurrency soak needs one auto-language case for each family: " + ", ".join(missing))
    return [selected[family] for family in REQUIRED]


async def _run_one(case: dict[str, Any], model: str, stagger_seconds: float) -> dict[str, Any]:
    # Small deterministic staggering makes the expected FIFO order explicit
    # without reducing overlap: later jobs enter the gate while the first model
    # is still loading/decoding.
    await asyncio.sleep(stagger_seconds)
    started = time.perf_counter()
    try:
        detected, segments = await transcribe(
            Path(case["media"]),
            model_name=model,
            language_hint="auto",
        )
        return {
            "id": case["id"],
            "family": case["family"],
            "detected_language": detected,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "transcript_chars": len(transcript_text(segments)),
            "passed": bool(segments),
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "family": case["family"],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def run(manifest: Path, model: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.transcription_backend != "faster-whisper":
        raise RuntimeError("Concurrency soak must use TRANSCRIPTION_BACKEND=faster-whisper.")
    if int(settings.asr_concurrency) != 1:
        raise RuntimeError("Production FIFO soak expects ASR_CONCURRENCY=1.")

    cases = _load_cases(manifest)
    done = asyncio.Event()
    running_order: list[str] = []
    max_queue_size = 0
    max_active = 0
    samples = 0

    async def monitor() -> None:
        nonlocal max_queue_size, max_active, samples
        while not done.is_set():
            overview = asr_queue_overview()
            max_queue_size = max(max_queue_size, int(overview.get("queue_size", 0)))
            max_active = max(max_active, int(overview.get("asr_active", 0)))
            samples += 1
            for case in cases:
                snapshot = asr_queue_snapshot(Path(case["media"]))
                if snapshot and snapshot.get("asr_state") == "running" and case["family"] not in running_order:
                    running_order.append(case["family"])
            await asyncio.sleep(0.05)

    started = time.perf_counter()
    monitor_task = asyncio.create_task(monitor())
    tasks = [
        asyncio.create_task(_run_one(case, model, index * 0.08))
        for index, case in enumerate(cases)
    ]
    try:
        results = await asyncio.gather(*tasks)
    finally:
        done.set()
        await monitor_task
    elapsed = time.perf_counter() - started
    final_overview = asr_queue_overview()

    expected_order = list(REQUIRED)
    checks = {
        "all_transcriptions_succeeded": all(item.get("passed") for item in results),
        "queue_was_exercised": max_queue_size >= 2,
        "never_exceeded_concurrency": max_active <= 1 and max_active >= 1,
        "fifo_order_observed": running_order == expected_order,
        "gate_drained": int(final_overview.get("queue_size", 0)) == 0 and int(final_overview.get("asr_active", 0)) == 0,
    }
    passed = all(checks.values())
    return {
        "soak_version": "2026-08-11-v2",
        "qualification_contract_version": QUALIFICATION_CONTRACT_VERSION,
        "threshold_sha256": threshold_contract_sha256(),
        "model": model,
        "secondary_model": settings.whisper_secondary_model,
        "require_asr_consensus": settings.require_asr_consensus,
        "asr_concurrency": settings.asr_concurrency,
        "expected_fifo_order": expected_order,
        "observed_fifo_order": running_order,
        "max_queue_size": max_queue_size,
        "max_active": max_active,
        "monitor_samples": samples,
        "elapsed_seconds": round(elapsed, 3),
        "final_overview": final_overview,
        "checks": checks,
        "passed": passed,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run three real Whisper requests concurrently through ClipKaro's FIFO ASR gate.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "medium"))
    parser.add_argument("--output", default="asr-concurrency-report.json")
    args = parser.parse_args()

    try:
        report = asyncio.run(run(Path(args.manifest).resolve(), args.model))
    except Exception as exc:
        print(f"ASR concurrency soak could not run: {exc}", file=sys.stderr)
        return 3

    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "max_queue_size": report["max_queue_size"],
        "max_active": report["max_active"],
        "observed_fifo_order": report["observed_fifo_order"],
        "checks": report["checks"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

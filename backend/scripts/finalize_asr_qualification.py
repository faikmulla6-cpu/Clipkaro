#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCK_FILE = ROOT / "asr-threshold-lock.json"


def _frozen_threshold_contract() -> tuple[dict[str, Any], str]:
    payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    contract = payload["contract"]
    encoded = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != payload.get("threshold_sha256"):
        raise RuntimeError("Source-controlled ASR threshold lock is internally inconsistent.")
    return contract, actual



EXCLUDED_DIRS = {".git", ".venv-ci", "node_modules", ".next", "__pycache__", ".pytest_cache", "stress_corpus"}
EXCLUDED_PREFIXES = ("backend/storage/models/", "backend/storage/uploads/", "backend/storage/exports/")
EXCLUDED_NAMES = {
    "asr-execution-preflight.json", "asr-stress-report.json", "asr-cafe-report.json", "asr-fan-report.json",
    "asr-hinted-report.json", "asr-concurrency-report.json", "asr-runner-hardware.txt",
}


def _json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_tree_sha256() -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        parts = set(path.relative_to(REPO_ROOT).parts)
        if parts & EXCLUDED_DIRS:
            continue
        if relative.startswith(EXCLUDED_PREFIXES):
            continue
        if path.name in EXCLUDED_NAMES or relative.startswith("backend/asr-qualification-evidence/"):
            continue
        files.append(path)
    for path in sorted(files, key=lambda item: item.relative_to(REPO_ROOT).as_posix()):
        relative = path.relative_to(REPO_ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        file_digest = bytes.fromhex(_sha256(path))
        digest.update(file_digest)
    return digest.hexdigest()


def _git_identity() -> dict[str, Any]:
    expected = os.environ.get("TESTED_SHA", "").strip()
    result: dict[str, Any] = {"expected_sha": expected or None, "git_sha": None, "clean": None, "exact_sha_match": False}
    try:
        head = subprocess.check_output(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        porcelain = subprocess.check_output(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--untracked-files=no"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        result["reason"] = "git_metadata_unavailable"
        return result
    result["git_sha"] = head
    result["clean"] = not porcelain.strip()
    result["exact_sha_match"] = bool(head and (not expected or head == expected))
    if expected and head != expected:
        result["reason"] = "tested_sha_mismatch"
    elif not result["clean"]:
        result["reason"] = "working_tree_dirty"
    return result


def _resource(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "elapsed_wall": r"Elapsed \(wall clock\) time.*\):\s*([0-9:.]+)",
        "max_rss_kb": r"Maximum resident set size \(kbytes\):\s*(\d+)",
        "user_seconds": r"User time \(seconds\):\s*([0-9.]+)",
        "system_seconds": r"System time \(seconds\):\s*([0-9.]+)",
        "cpu_percent": r"Percent of CPU this job got:\s*([^\n]+)",
        "exit_status": r"Exit status:\s*(\d+)",
    }
    parsed: dict[str, Any] = {"file": path.name, "sha256": _sha256(path)}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            value: Any = match.group(1).strip()
            if key in {"max_rss_kb", "exit_status"}:
                value = int(value)
            elif key in {"user_seconds", "system_seconds"}:
                value = float(value)
            parsed[key] = value
    return parsed


def _matrix(core: dict[str, Any] | None) -> dict[str, Any]:
    if not core:
        return {}
    summary = core.get("summary", {}).get("scenarios", {}) or {}
    matrix: dict[str, Any] = {}
    for scenario_name, scenario in summary.items():
        matrix[scenario_name] = {
            "passed": bool(scenario.get("passed")),
            "aggregate": {
                key: scenario.get(key)
                for key in ("cases", "successful_cases", "success_rate", "p90_wer", "p90_cer", "p95_rtf", "worst_wer", "worst_cer", "language_match_rate", "timestamp_valid_rate", "limits")
                if key in scenario
            },
            "by_language": {
                family: {
                    key: details.get(key)
                    for key in ("passed", "cases", "successful_cases", "success_rate", "p90_wer", "p90_cer", "p95_rtf", "worst_wer", "worst_cer", "language_match_rate", "timestamp_valid_rate", "limits")
                    if key in details
                }
                for family, details in (scenario.get("by_language", {}) or {}).items()
            },
        }
    return matrix


def _threshold_state(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    contract, current = _frozen_threshold_contract()
    before_sha = (before or {}).get("threshold_sha256")
    after_sha = (after or {}).get("threshold_sha256")
    unchanged = bool(before_sha and after_sha and before_sha == after_sha == current)
    return {
        "current_sha256": current,
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "unchanged_during_run": unchanged,
        "contract_version": contract.get("contract_version"),
        "contract": contract,
    }


def _noise_evidence(noise_manifest: dict[str, Any] | None) -> Any:
    return noise_manifest if noise_manifest is not None else None


def _decision(*, identity: dict[str, Any], threshold: dict[str, Any], preflight: Any, core: Any, cafe: Any, fan: Any, hinted: Any, concurrency: Any, hardware: Path, resources: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    failures: list[str] = []
    if not preflight:
        blockers.append("missing ASR execution preflight evidence")
    elif not bool(preflight.get("ready")):
        blockers.extend(f"execution environment: {item}" for item in (preflight.get("blockers") or []))
    if not identity.get("git_sha"):
        blockers.append("exact Git candidate SHA unavailable")
    elif not identity.get("exact_sha_match"):
        blockers.append("checked-out Git SHA does not match TESTED_SHA")
    if identity.get("clean") is False:
        blockers.append("Git working tree was not clean")
    if not threshold.get("unchanged_during_run"):
        blockers.append("ASR threshold lock was missing or changed during qualification")
    lock_sha = threshold.get("current_sha256")
    for report_name, report in (("core", core), ("cafe", cafe), ("fan", fan), ("hinted", hinted), ("concurrency", concurrency)):
        if report is not None and report.get("threshold_sha256") != lock_sha:
            blockers.append(f"{report_name} report threshold hash does not match the frozen qualification lock")
    required_artifacts = {
        "core qualification report": core,
        "cafe noise report": cafe,
        "fan noise report": fan,
        "hinted override report": hinted,
        "FIFO concurrency report": concurrency,
    }
    for name, value in required_artifacts.items():
        if value is None:
            blockers.append(f"missing {name}")
    if not hardware.exists():
        blockers.append("missing runner hardware evidence")
    for name, value in resources.items():
        if value is None:
            blockers.append(f"missing {name} resource evidence")
    if blockers:
        return "BLOCKED", blockers, failures

    if not bool(core.get("production_ready")):
        failures.append("core Hindi/Marathi/Hinglish qualification failed")
    if not bool(cafe.get("selected_scenarios_passed")):
        failures.append("cafe real-noise sweep failed")
    if not bool(fan.get("selected_scenarios_passed")):
        failures.append("fan real-noise sweep failed")
    if not bool(hinted.get("selected_scenarios_passed")):
        failures.append("explicit-language fallback sweep failed")
    if not bool(concurrency.get("passed")):
        failures.append("FIFO/concurrency soak failed")
    if failures:
        return "FAIL", blockers, failures
    return "PASS", blockers, failures


def _markdown(evidence: dict[str, Any]) -> str:
    lines = [
        "# ClipKaro real ASR qualification evidence",
        "",
        f"**Decision: {evidence['decision']}**",
        "",
        f"Generated: `{evidence['generated_at']}`",
        f"Git SHA: `{evidence['candidate']['git_sha'] or 'unavailable'}`",
        f"Source-tree SHA-256: `{evidence['candidate']['source_tree_sha256']}`",
        f"Threshold lock: `{evidence['threshold_lock']['current_sha256']}`",
        "",
    ]
    if evidence["blockers"]:
        lines += ["## Blockers", ""] + [f"- {item}" for item in evidence["blockers"]] + [""]
    if evidence["failures"]:
        lines += ["## Failed gates", ""] + [f"- {item}" for item in evidence["failures"]] + [""]
    lines += ["## Core scenario matrix", ""]
    for name, scenario in evidence.get("metrics", {}).get("core_matrix", {}).items():
        agg = scenario.get("aggregate", {})
        lines.append(
            f"- **{name}** — {'PASS' if scenario.get('passed') else 'FAIL'}; "
            f"p90 WER={agg.get('p90_wer', 'n/a')}, p90 CER={agg.get('p90_cer', 'n/a')}, "
            f"p95 RTF={agg.get('p95_rtf', 'n/a')}, success={agg.get('success_rate', 'n/a')}"
        )
        for family, detail in scenario.get("by_language", {}).items():
            lines.append(
                f"  - {family}: {'PASS' if detail.get('passed') else 'FAIL'}; "
                f"WER={detail.get('p90_wer', 'n/a')}, CER={detail.get('p90_cer', 'n/a')}, "
                f"RTF={detail.get('p95_rtf', 'n/a')}"
            )
    neg = evidence.get("negative_controls") or {}
    lines += ["", "## Hallucination controls", "", f"Passed: `{neg.get('passed', False)}`", ""]
    conc = evidence.get("concurrency") or {}
    lines += ["## FIFO/concurrency", "", f"Passed: `{conc.get('passed', False)}`", f"Checks: `{json.dumps(conc.get('checks', {}), sort_keys=True)}`", ""]
    lines += ["## Resource evidence", ""]
    for name, resource in evidence.get("resources", {}).items():
        if resource:
            lines.append(f"- {name}: max RSS={resource.get('max_rss_kb', 'n/a')} KiB; wall={resource.get('elapsed_wall', 'n/a')}; exit={resource.get('exit_status', 'n/a')}")
        else:
            lines.append(f"- {name}: missing")
    lines += ["", "Thresholds are source-controlled and hashed before and after inference. A PASS is impossible if the lock changes or exact candidate identity is unavailable."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize immutable real-ASR qualification evidence.")
    parser.add_argument("--evidence-dir", default="asr-qualification-evidence")
    parser.add_argument("--core", default="asr-stress-report.json")
    parser.add_argument("--cafe", default="asr-cafe-report.json")
    parser.add_argument("--fan", default="asr-fan-report.json")
    parser.add_argument("--hinted", default="asr-hinted-report.json")
    parser.add_argument("--concurrency", default="asr-concurrency-report.json")
    parser.add_argument("--hardware", default="asr-runner-hardware.txt")
    parser.add_argument("--preflight", default="asr-execution-preflight.json")
    parser.add_argument("--noise-manifest", default="stress_corpus/noise/noise-manifest.json")
    parser.add_argument("--threshold-before", default="asr-qualification-evidence/threshold-lock-before.json")
    parser.add_argument("--threshold-after", default="asr-qualification-evidence/threshold-lock-after.json")
    parser.add_argument("--enforce", action="store_true", help="Return nonzero unless the final decision is PASS.")
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    core = _json(Path(args.core))
    cafe = _json(Path(args.cafe))
    fan = _json(Path(args.fan))
    hinted = _json(Path(args.hinted))
    concurrency = _json(Path(args.concurrency))
    before = _json(Path(args.threshold_before))
    after = _json(Path(args.threshold_after))
    hardware = Path(args.hardware)
    preflight = _json(Path(args.preflight))
    resources = {
        "core": _resource(Path("asr-core-resource.txt")),
        "cafe": _resource(Path("asr-cafe-resource.txt")),
        "fan": _resource(Path("asr-fan-resource.txt")),
        "hinted": _resource(Path("asr-hinted-resource.txt")),
        "concurrency": _resource(Path("asr-concurrency-resource.txt")),
    }
    identity = _git_identity()
    identity["source_tree_sha256"] = _source_tree_sha256()
    threshold = _threshold_state(before, after)
    decision, blockers, failures = _decision(
        identity=identity, threshold=threshold, preflight=preflight, core=core, cafe=cafe, fan=fan,
        hinted=hinted, concurrency=concurrency, hardware=hardware, resources=resources,
    )

    evidence = {
        "schema_version": "clipkaro-asr-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "candidate": identity,
        "threshold_lock": threshold,
        "blockers": blockers,
        "failures": failures,
        "execution_preflight": preflight,
        "configuration": {
            "primary_model": (core or {}).get("model") or os.environ.get("WHISPER_MODEL", "medium"),
            "secondary_model": (core or {}).get("secondary_model") or os.environ.get("WHISPER_SECONDARY_MODEL", "small"),
            "alignment_backend": (core or {}).get("alignment_backend") or os.environ.get("ALIGNMENT_BACKEND", "whisperx"),
            "asr_concurrency": os.environ.get("ASR_CONCURRENCY", "1"),
        },
        "corpus": (core or {}).get("corpus"),
        "corpus_cases": (core or {}).get("corpus_cases"),
        "noise": _noise_evidence(_json(Path(args.noise_manifest))),
        "metrics": {"core_matrix": _matrix(core), "raw_case_count": len((core or {}).get("results", []) or [])},
        "negative_controls": (core or {}).get("negative_controls"),
        "environmental_sweeps": {
            "cafe": {"passed": bool((cafe or {}).get("selected_scenarios_passed")), "summary": (cafe or {}).get("summary")},
            "fan": {"passed": bool((fan or {}).get("selected_scenarios_passed")), "summary": (fan or {}).get("summary")},
        },
        "hinted_override": {"passed": bool((hinted or {}).get("selected_scenarios_passed")), "summary": (hinted or {}).get("summary")},
        "concurrency": concurrency,
        "resources": resources,
        "hardware": {
            "file": hardware.name if hardware.exists() else None,
            "sha256": _sha256(hardware) if hardware.exists() else None,
            "text": hardware.read_text(encoding="utf-8", errors="replace") if hardware.exists() else None,
        },
    }
    json_path = evidence_dir / "asr-qualification-evidence.json"
    md_path = evidence_dir / "asr-qualification-summary.md"
    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(evidence), encoding="utf-8")
    print(json.dumps({"decision": decision, "blockers": blockers, "failures": failures, "evidence": str(json_path)}, ensure_ascii=False, indent=2))
    if args.enforce:
        return 0 if decision == "PASS" else (2 if decision == "FAIL" else 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

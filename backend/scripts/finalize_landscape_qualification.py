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

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.landscape_qualification import (  # noqa: E402
    CASE_COUNT,
    EXPORTS_REQUIRED,
    POLICIES,
    report_is_complete,
    threshold_contract_sha256,
)


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



EXCLUDED_DIRS = {
    ".git", ".venv-ci", "node_modules", ".next", "__pycache__", ".pytest_cache",
    "landscape_qa", "landscape-qualification-evidence",
}
EXCLUDED_RUNTIME_NAMES = {
    "landscape-execution-preflight.json",
    "landscape-runner-hardware.txt",
    "landscape-qa-resource.txt",
}


def _source_tree_sha256() -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if set(relative.parts) & EXCLUDED_DIRS:
            continue
        if path.name in EXCLUDED_RUNTIME_NAMES:
            continue
        files.append(path)
    for path in sorted(files, key=lambda item: item.relative_to(REPO_ROOT).as_posix()):
        relative = path.relative_to(REPO_ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def _git_identity() -> dict[str, Any]:
    expected = os.environ.get("TESTED_SHA") or None
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=REPO_ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return {
            "git_checkout": True,
            "head_sha": head,
            "expected_sha": expected,
            "exact_sha": bool(expected and head == expected),
            "tracked_tree_clean": not dirty,
        }
    except Exception:
        return {
            "git_checkout": False,
            "head_sha": None,
            "expected_sha": expected,
            "exact_sha": False,
            "tracked_tree_clean": None,
        }


def _resource(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    fields: dict[str, Any] = {"file": path.name, "sha256": _sha256(path)}
    patterns = {
        "elapsed": r"Elapsed \(wall clock\) time[^:]*:\s*(.+)",
        "max_rss_kib": r"Maximum resident set size \(kbytes\):\s*(\d+)",
        "cpu_percent": r"Percent of CPU this job got:\s*(.+)",
        "exit_status": r"Exit status:\s*(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            fields[key] = int(value) if key in {"max_rss_kib", "exit_status"} else value
    return fields


def _artifact_integrity(report: dict[str, Any] | None, output_root: Path) -> list[str]:
    """Verify the report still points at the exact real inputs/cases/MP4s it measured."""
    if not isinstance(report, dict):
        return []
    failures: list[str] = []

    for source in report.get("sources") or []:
        filename = str(source.get("filename") or "")
        expected = str(source.get("sha256") or "")
        path = output_root / "downloads" / filename
        if not filename or not path.is_file():
            failures.append(f"source artifact missing: {filename or 'unknown'}")
            continue
        if len(expected) != 64 or _sha256(path) != expected:
            failures.append(f"source SHA-256 mismatch: {filename}")

    for case in report.get("cases") or []:
        case_id = str(case.get("id") or "")
        expected = str(case.get("case_sha256") or "")
        path = output_root / "cases" / f"{case_id}.mp4"
        if not case_id or not path.is_file():
            failures.append(f"normalized case artifact missing: {case_id or 'unknown'}")
            continue
        if len(expected) != 64 or _sha256(path) != expected:
            failures.append(f"normalized case SHA-256 mismatch: {case_id}")

    seen: set[str] = set()
    for export in report.get("exports") or []:
        relative = str(export.get("path") or "")
        expected = str(export.get("sha256") or "")
        if not relative or relative in seen:
            failures.append("export path is missing or duplicated")
            continue
        seen.add(relative)
        path = output_root / relative
        if not path.is_file():
            failures.append(f"export artifact missing: {relative}")
            continue
        if len(expected) != 64 or _sha256(path) != expected:
            failures.append(f"export SHA-256 mismatch: {relative}")
        if int(export.get("size_bytes") or 0) != path.stat().st_size:
            failures.append(f"export byte-size mismatch: {relative}")

    return failures


def _threshold_state(before: Any, after: Any) -> dict[str, Any]:
    expected = threshold_contract_sha256()
    before_hash = (before or {}).get("threshold_sha256")
    after_hash = (after or {}).get("threshold_sha256")
    return {
        "expected_sha256": expected,
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "unchanged": bool(before_hash == expected and after_hash == expected),
    }


def _decision(
    *,
    identity: dict[str, Any],
    threshold: dict[str, Any],
    preflight: dict[str, Any] | None,
    report: dict[str, Any] | None,
    resource: dict[str, Any] | None,
    artifact_failures: list[str],
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    failures: list[str] = []

    if not identity["git_checkout"]:
        blockers.append("qualification did not run from a Git checkout")
    elif not identity["exact_sha"]:
        failures.append("tested Git SHA does not match TESTED_SHA")
    if identity.get("tracked_tree_clean") is False:
        failures.append("tracked source tree was dirty")

    if not threshold["unchanged"]:
        failures.append("landscape threshold lock changed or was not recorded before/after execution")

    if not preflight or not preflight.get("ready"):
        blockers.extend(str(item) for item in (preflight or {}).get("blockers", []) if item)
        if not preflight:
            blockers.append("landscape execution preflight is missing")

    if report is None:
        if blockers:
            return "BLOCKED", list(dict.fromkeys(blockers)), failures
        failures.append("30-export landscape report is missing")
    else:
        complete, report_failures = report_is_complete(report)
        if not complete:
            failures.extend(report_failures)
        failures.extend(artifact_failures)
        if not resource:
            failures.append("GNU time resource evidence is missing")

    if failures:
        return "FAIL", list(dict.fromkeys(blockers)), list(dict.fromkeys(failures))
    if blockers:
        return "BLOCKED", list(dict.fromkeys(blockers)), []
    return "PASS", [], []


def _markdown(evidence: dict[str, Any]) -> str:
    report = evidence.get("report") or {}
    summary = report.get("summary") or {}
    lines = [
        "# ClipKaro real landscape qualification",
        "",
        f"**Execution decision:** `{evidence['decision']}`",
        f"**Product framing verdict:** `{summary.get('verdict') or 'NOT_AVAILABLE'}`",
        "",
        f"- Tested SHA: `{evidence['candidate'].get('head_sha') or 'not-a-git-checkout'}`",
        f"- Threshold lock unchanged: **{evidence['threshold_lock'].get('unchanged')}**",
        f"- Real cases: **{report.get('case_count', 0)} / {CASE_COUNT}**",
        f"- Exports: **{report.get('successful_export_count', 0)} / {EXPORTS_REQUIRED} validated**",
        f"- Reliably face-scored cases: **{summary.get('scored_cases', 0)} / {CASE_COUNT}**",
        f"- Center pass rate: **{float(summary.get('default_case_pass_rate') or 0):.0%}**",
        f"- Manual pass rate: **{float(summary.get('manual_case_pass_rate') or 0):.0%}**",
        f"- Dynamic pass rate: **{float(summary.get('dynamic_case_pass_rate') or 0):.0%}**",
        f"- Dynamic-only rescue rate: **{float(summary.get('dynamic_only_rescue_rate') or 0):.0%}**",
        f"- Multi-face sampled-frame rate: **{float(summary.get('multi_face_sample_rate') or 0):.0%}**",
        "",
    ]
    if evidence["blockers"]:
        lines += ["## Blockers", ""] + [f"- {item}" for item in evidence["blockers"]] + [""]
    if evidence["failures"]:
        lines += ["## Failures", ""] + [f"- {item}" for item in evidence["failures"]] + [""]
    multi = summary.get("multi_face_case_ids") or []
    if multi:
        lines += ["## Multi-face cases", ""] + [f"- `{item}`" for item in multi] + [""]
    if report.get("cases"):
        lines += [
            "## Case framing matrix",
            "",
            "| Case | Detection | Multi-face | Center | Manual | Dynamic |",
            "| --- | ---: | ---: | --- | --- | --- |",
        ]
        for case in report["cases"]:
            lines.append(
                f"| {case.get('id')} | {float((case.get('detection') or {}).get('detection_coverage') or 0):.0%} | "
                f"{int(case.get('multi_face_samples') or 0)} | "
                f"{'PASS' if (case.get('default') or {}).get('passed') else 'FAIL'} | "
                f"{'PASS' if (case.get('manual') or {}).get('passed') else 'FAIL'} | "
                f"{'PASS' if (case.get('dynamic') or {}).get('passed') else 'FAIL'} |"
            )
        lines.append("")
    lines += [
        "A `PASS` execution decision means the 10×3 real export matrix is complete and trustworthy.",
        "It does not force the product verdict to favor manual or automatic reframing; red framing behavior remains valid product evidence.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize ClipKaro's exact-SHA 30-export landscape qualification evidence.")
    parser.add_argument("--evidence-dir", default="landscape-qualification-evidence")
    parser.add_argument("--report", default="landscape_qa/landscape-export-qa-report.json")
    parser.add_argument("--preflight", default="landscape-execution-preflight.json")
    parser.add_argument("--resource", default="landscape-qa-resource.txt")
    parser.add_argument("--threshold-before", default="landscape-qualification-evidence/threshold-lock-before.json")
    parser.add_argument("--threshold-after", default="landscape-qualification-evidence/threshold-lock-after.json")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)
    report = _json(report_path)
    preflight = _json(Path(args.preflight))
    before = _json(Path(args.threshold_before))
    after = _json(Path(args.threshold_after))
    threshold = _threshold_state(before, after)
    identity = _git_identity()
    identity["source_tree_sha256"] = _source_tree_sha256()
    resource = _resource(Path(args.resource))
    artifact_failures = _artifact_integrity(report, report_path.parent)

    decision, blockers, failures = _decision(
        identity=identity,
        threshold=threshold,
        preflight=preflight,
        report=report,
        resource=resource,
        artifact_failures=artifact_failures,
    )
    evidence = {
        "schema_version": "clipkaro-landscape-qualification-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "candidate": identity,
        "threshold_lock": threshold,
        "blockers": blockers,
        "failures": failures,
        "execution_preflight": preflight,
        "resource": resource,
        "report": report,
        "product_verdict": (report or {}).get("summary"),
    }
    json_path = evidence_dir / "landscape-qualification-evidence.json"
    md_path = evidence_dir / "landscape-qualification-summary.md"
    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(evidence), encoding="utf-8")
    print(json.dumps(
        {
            "decision": decision,
            "product_verdict": ((report or {}).get("summary") or {}).get("verdict"),
            "blockers": blockers,
            "failures": failures,
            "evidence": str(json_path),
        },
        ensure_ascii=False,
        indent=2,
    ))
    if args.enforce:
        return 0 if decision == "PASS" else (2 if decision == "FAIL" else 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

MANDATORY_CHECKS = (
    "execution_preflight",
    "clean_checkout",
    "runner_prerequisites",
    "backend_environment",
    "backend_dependencies",
    "release_identity",
    "python_compile",
    "pip_check",
    "backend_tests",
    "production_preflight",
    "production_configuration",
    "npm_ci",
    "settings_trust",
    "analytics_truth",
    "billing_lifecycle",
    "email_verification",
    "security_foundation",
    "legal_privacy",
    "behavioral_learning",
    "landscape_reframe",
    "release_identity_postinstall",
    "npm_audit",
    "frontend_build",
    "compose_validate",
    "caddy_validate",
    "backend_api_image",
    "backend_worker_image",
    "worker_alignment_runtime",
    "frontend_image",
    "source_unchanged_after_checks",
    "docker_image_identity",
)
VALID_OUTCOMES = {"success", "failure", "blocked", "skipped"}
MIN_BACKEND_TESTS = 150


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _versions() -> tuple[str, str]:
    source = _read("backend/app/core/version.py")
    match = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", source)
    if not match:
        raise RuntimeError("Could not read backend APP_VERSION")
    frontend = json.loads(_read("frontend/package.json"))
    return match.group(1), str(frontend.get("version") or "")


def _git_safe(*args: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=30)
    except Exception as exc:
        return {"ok": False, "value": None, "error": type(exc).__name__}
    if proc.returncode != 0:
        return {"ok": False, "value": None, "error": (proc.stderr or "git command failed").strip()[:500]}
    return {"ok": True, "value": proc.stdout.strip(), "error": None}


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _pytest_summary() -> dict[str, Any]:
    path = ROOT / "backend" / "pytest-report.xml"
    if not path.exists():
        return {"available": False, "sha256": None}
    try:
        root = ET.parse(path).getroot()
        attrs = root.attrib
        if root.tag == "testsuites":
            suites = list(root)
            tests = sum(int(item.attrib.get("tests", 0)) for item in suites)
            failures = sum(int(item.attrib.get("failures", 0)) for item in suites)
            errors = sum(int(item.attrib.get("errors", 0)) for item in suites)
            skipped = sum(int(item.attrib.get("skipped", 0)) for item in suites)
            time_seconds = sum(float(item.attrib.get("time", 0) or 0) for item in suites)
        else:
            tests = int(attrs.get("tests", 0))
            failures = int(attrs.get("failures", 0))
            errors = int(attrs.get("errors", 0))
            skipped = int(attrs.get("skipped", 0))
            time_seconds = float(attrs.get("time", 0) or 0)
        return {
            "available": True,
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "time_seconds": time_seconds,
            "sha256": _sha256_file(path),
        }
    except Exception as exc:
        return {"available": False, "error": type(exc).__name__, "sha256": _sha256_file(path)}


def _npm_audit_summary() -> dict[str, Any]:
    path = ROOT / "frontend" / "npm-audit-production.json"
    payload = _load_json(path)
    if payload is None:
        return {"available": False, "sha256": _sha256_file(path)}
    metadata = payload.get("metadata")
    vulnerabilities = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(vulnerabilities, dict) or "high" not in vulnerabilities or "critical" not in vulnerabilities:
        return {"available": False, "error": "npm audit metadata.vulnerabilities is missing or malformed", "sha256": _sha256_file(path)}
    return {
        "available": True,
        "vulnerabilities": vulnerabilities,
        "dependencies": metadata.get("dependencies") or {},
        "high": int(vulnerabilities.get("high", 0) or 0),
        "critical": int(vulnerabilities.get("critical", 0) or 0),
        "sha256": _sha256_file(path),
    }


def _parse_checks(values: list[str]) -> dict[str, str]:
    checks: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid check outcome {value!r}; expected name=outcome")
        name, outcome = value.split("=", 1)
        name, outcome = name.strip(), outcome.strip().lower()
        if not name or not outcome:
            raise ValueError(f"Invalid check outcome {value!r}")
        if name in checks:
            raise ValueError(f"Duplicate check outcome supplied for {name!r}")
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome {outcome!r} for {name!r}; expected one of {sorted(VALID_OUTCOMES)}")
        checks[name] = outcome
    return checks


def _identity(expected_version: str) -> dict[str, Any]:
    backend_version, frontend_version = _versions()
    head = _git_safe("rev-parse", "HEAD")
    tree = _git_safe("rev-parse", "HEAD^{tree}")
    diff = _git_safe("status", "--porcelain", "--untracked-files=no")
    checked_out_sha = str(head.get("value") or "")
    tested_sha = os.environ.get("TESTED_SHA", checked_out_sha).strip()
    base_sha = os.environ.get("BASE_SHA", "").strip() or None
    exact_sha_shape = bool(re.fullmatch(r"[0-9a-f]{40}", tested_sha))
    return {
        "expected_version": expected_version,
        "backend_version": backend_version,
        "frontend_version": frontend_version,
        "version_parity": backend_version == frontend_version,
        "expected_version_matches": backend_version == frontend_version == expected_version,
        "git_available": bool(head.get("ok")),
        "tested_sha": tested_sha or None,
        "checked_out_sha": checked_out_sha or None,
        "source_tree_sha": tree.get("value") if tree.get("ok") else None,
        "sha_has_full_shape": exact_sha_shape,
        "sha_matches_checkout": bool(checked_out_sha and tested_sha == checked_out_sha and exact_sha_shape),
        "base_sha": base_sha,
        "tracked_source_unchanged_before_evidence": bool(diff.get("ok") and not diff.get("value")),
        "unexpected_tracked_paths": str(diff.get("value") or "").splitlines()[:50],
        "git_error": head.get("error") if not head.get("ok") else None,
    }


def _canonical_digest(payload: dict[str, Any]) -> str:
    clean = {key: value for key, value in payload.items() if key != "evidence_sha256"}
    raw = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _certification_analysis(
    *,
    identity: dict[str, Any],
    checks: dict[str, str],
    execution_preflight: dict[str, Any] | None,
    pytest_data: dict[str, Any],
    npm_data: dict[str, Any],
    docker_images: dict[str, Any] | None,
    workflow: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    failures: list[str] = []

    supplied = set(checks)
    required = set(MANDATORY_CHECKS)
    missing = sorted(required - supplied)
    unknown = sorted(supplied - required)
    if missing:
        blockers.append("mandatory check outcomes missing: " + ", ".join(missing))
    if unknown:
        blockers.append("unknown check outcomes supplied: " + ", ".join(unknown))

    if execution_preflight is None:
        blockers.append("Fresh Launch execution-preflight evidence is missing")
    elif not bool(execution_preflight.get("ready")):
        blockers.extend(f"execution environment: {item}" for item in (execution_preflight.get("blockers") or ["not ready"]))

    if not identity.get("git_available"):
        blockers.append("exact Git checkout unavailable")
    else:
        if not identity.get("sha_matches_checkout"):
            blockers.append("TESTED_SHA is not the exact 40-character checked-out Git SHA")
        if not identity.get("tracked_source_unchanged_before_evidence"):
            blockers.append("tracked source changed during Fresh Launch QA")
    if not identity.get("version_parity") or not identity.get("expected_version_matches"):
        failures.append("backend/frontend release identity does not exactly match expected version")

    if not workflow.get("run_id"):
        blockers.append("GitHub workflow run ID is missing; certification must be tied to an immutable workflow artifact")
    elif workflow.get("repository") != "faikmulla6-cpu/Clipkaro":
        blockers.append("GitHub repository identity does not match faikmulla6-cpu/Clipkaro")

    if checks.get("backend_tests") == "success":
        if not pytest_data.get("available"):
            blockers.append("backend_tests reported success but pytest XML evidence is missing")
        elif int(pytest_data.get("tests", 0)) < MIN_BACKEND_TESTS:
            failures.append(f"complete backend suite evidence is too small: {pytest_data.get('tests', 0)} tests, minimum contract is {MIN_BACKEND_TESTS}")
        elif int(pytest_data.get("failures", 0)) or int(pytest_data.get("errors", 0)):
            failures.append("pytest evidence contains failures/errors despite backend_tests success")
    if checks.get("npm_audit") == "success":
        if not npm_data.get("available"):
            blockers.append("npm_audit reported success but audit JSON evidence is missing")
        elif int(npm_data.get("high", 0)) or int(npm_data.get("critical", 0)):
            failures.append("production npm audit contains high/critical vulnerabilities")

    if checks.get("docker_image_identity") == "success":
        if docker_images is None:
            blockers.append("docker_image_identity reported success but image evidence is missing")
        else:
            images = docker_images.get("images") or {}
            for name in ("api", "worker", "frontend"):
                item = images.get(name) or {}
                if not item.get("image_id") or not item.get("repo_digest_or_id"):
                    blockers.append(f"Docker identity evidence incomplete for {name} image")
                if item.get("os") != "linux" or item.get("architecture") not in {"amd64", "x86_64"}:
                    blockers.append(f"Docker image platform is not linux/amd64 for {name}")

    if blockers:
        return "BLOCKED", blockers, failures

    red = [name for name in MANDATORY_CHECKS if checks.get(name) != "success"]
    if red:
        failures.append("mandatory checks not successful: " + ", ".join(red))
    if failures:
        return "FAIL", blockers, failures
    return "CERTIFIED", blockers, failures


def _render_certification_record(report: dict[str, Any]) -> str:
    status = "LAUNCH-CERTIFIED ✅" if report["certified"] else f"LAUNCH-{report['decision']} ❌"
    checks = report.get("checks") or {}
    check_lines = [
        f"- {'✅' if checks.get(name) == 'success' else '❌'} `{name}` — `{checks.get(name, 'missing')}`"
        for name in MANDATORY_CHECKS
    ]
    backend = report.get("backend_tests") or {}
    audit = report.get("npm_production_audit") or {}
    lines = [
        f"# ClipKaro {report['release_version']} Fresh Launch QA certification record",
        "",
        f"**Status: {status}**",
        "",
        f"- Exact tested SHA: `{report['identity'].get('tested_sha') or 'unavailable'}`",
        f"- Source tree: `{report['identity'].get('source_tree_sha') or 'unavailable'}`",
        f"- Workflow run: `{report['workflow'].get('run_id') or 'unavailable'}`",
        f"- Generated UTC: `{report['generated_at_utc']}`",
        f"- Evidence SHA-256: `{report['evidence_sha256']}`",
        f"- Backend tests: `{backend.get('tests', 0)}` total, `{backend.get('failures', 0)}` failures, `{backend.get('errors', 0)}` errors",
        f"- npm high/critical: `{audit.get('high', 'n/a')}` / `{audit.get('critical', 'n/a')}`",
        "",
        "## Mandatory checks",
        "",
        *check_lines,
        "",
    ]
    if report.get("blockers"):
        lines += ["## Blockers", "", *[f"- {item}" for item in report["blockers"]], ""]
    if report.get("failures"):
        lines += ["## Failed gates", "", *[f"- {item}" for item in report["failures"]], ""]
    lines += [
        "## Certification boundary",
        "",
        "This record certifies only the exact build/deployment candidate above. Real ASR, real landscape framing, main-branch protection and live production/operator/payment configuration remain separate launch gates.",
        "",
        "A tracked source file is intentionally not rewritten to say LAUNCH-CERTIFIED after the run, because doing so would create a new Git SHA that was not the SHA tested. This immutable artifact is the certification record for the tested SHA.",
        "",
    ]
    return "\n".join(lines)


def generate(args: argparse.Namespace) -> int:
    checks = _parse_checks(args.check)
    identity = _identity(args.expected_version)
    execution_preflight = _load_json(ROOT / args.execution_preflight)
    docker_images = _load_json(ROOT / args.docker_evidence)
    pytest_data = _pytest_summary()
    npm_data = _npm_audit_summary()
    workflow = {
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "actor": os.environ.get("GITHUB_ACTOR"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "ref": os.environ.get("GITHUB_REF"),
    }
    decision, blockers, failures = _certification_analysis(
        identity=identity,
        checks=checks,
        execution_preflight=execution_preflight,
        pytest_data=pytest_data,
        npm_data=npm_data,
        docker_images=docker_images,
        workflow=workflow,
    )
    report: dict[str, Any] = {
        "schema": "clipkaro.launch-qa.v2",
        "release_version": args.expected_version,
        "certified": decision == "CERTIFIED",
        "decision": decision,
        "launch_certification": "LAUNCH-CERTIFIED" if decision == "CERTIFIED" else f"LAUNCH-{decision}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "faikmulla6-cpu/Clipkaro",
        "workflow": workflow,
        "identity": identity,
        "mandatory_checks": list(MANDATORY_CHECKS),
        "checks": checks,
        "blockers": blockers,
        "failures": failures,
        "execution_preflight": execution_preflight,
        "backend_tests": pytest_data,
        "npm_production_audit": npm_data,
        "docker_images": docker_images,
        "warnings": [line for line in os.environ.get("QA_WARNINGS", "").split("\n") if line.strip()],
        "separate_empirical_gates": [
            "real ASR acoustic qualification (#21)",
            "landscape podcast framing qualification (#22)",
            "GitHub main ruleset (#25)",
            "live production credentials/operator/payment deployment (#30)",
        ],
    }
    report["evidence_sha256"] = _canonical_digest(report)

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "launch-qa-evidence.json"
    md_path = output_dir / "launch-qa-summary.md"
    status_path = output_dir / "QA_REPORT.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    rendered = _render_certification_record(report)
    md_path.write_text(rendered, encoding="utf-8")
    status_path.write_text(rendered, encoding="utf-8")
    print(json.dumps({"decision": decision, "tested_sha": identity.get("tested_sha"), "evidence_sha256": report["evidence_sha256"], "blockers": blockers, "failures": failures}, indent=2))
    return 0


def enforce(args: argparse.Namespace) -> int:
    path = ROOT / args.report
    payload = _load_json(path)
    if payload is None:
        print("Fresh Launch QA report is missing or invalid JSON.", file=sys.stderr)
        return 1
    expected_digest = payload.get("evidence_sha256")
    actual_digest = _canonical_digest(payload)
    if not expected_digest or expected_digest != actual_digest:
        print("Fresh Launch QA evidence digest mismatch; report may be incomplete or tampered.", file=sys.stderr)
        return 1
    if payload.get("schema") != "clipkaro.launch-qa.v2":
        print("Fresh Launch QA evidence schema is not the current v2 contract.", file=sys.stderr)
        return 1
    checks = payload.get("checks") or {}
    if set(checks) != set(MANDATORY_CHECKS):
        print("Fresh Launch QA evidence does not contain the exact mandatory check set.", file=sys.stderr)
        return 1
    if (
        payload.get("certified") is True
        and payload.get("decision") == "CERTIFIED"
        and payload.get("launch_certification") == "LAUNCH-CERTIFIED"
        and all(checks.get(name) == "success" for name in MANDATORY_CHECKS)
    ):
        print(f"Fresh Launch QA LAUNCH-CERTIFIED {payload.get('release_version')} at {payload.get('identity', {}).get('tested_sha')}")
        return 0
    print(
        f"Fresh Launch QA is {payload.get('decision', 'NOT_CERTIFIED')}. "
        f"Blockers={payload.get('blockers', [])}; failures={payload.get('failures', [])}",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or enforce exact-SHA ClipKaro Fresh Launch QA evidence.")
    sub = parser.add_subparsers(dest="command", required=True)

    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--expected-version", default="7.8.0")
    generate_parser.add_argument("--output-dir", default="launch-qa")
    generate_parser.add_argument("--execution-preflight", default="launch-qa/execution-preflight.json")
    generate_parser.add_argument("--docker-evidence", default="launch-qa/docker-images.json")
    generate_parser.add_argument("--check", action="append", default=[])
    generate_parser.set_defaults(func=generate)

    enforce_parser = sub.add_parser("enforce")
    enforce_parser.add_argument("--report", default="launch-qa/launch-qa-evidence.json")
    enforce_parser.set_defaults(func=enforce)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

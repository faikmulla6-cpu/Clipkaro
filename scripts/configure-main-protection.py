#!/usr/bin/env python3
"""Create/update ClipKaro's active GitHub `main` ruleset with no secret persistence.

Prerequisite:
  gh auth login
The authenticated account/token must have repository Administration: write.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "faikmulla6-cpu/Clipkaro"
DEFAULT_BRANCH = "main"
RULESET_FILE = ROOT / ".github" / "main-protection-ruleset.json"
RULESET_NAME = "ClipKaro main protection"

EXPECTED_CHECKS = [
    "PR Governance",
    "Critical Backend Invariants",
    "Critical Frontend Contracts",
    "Backend CI",
    "Frontend CI",
]

def run(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, input=input_text, text=True, capture_output=True, check=check
    )

def gh_api(repo: str, path: str, method: str = "GET", payload: dict | None = None):
    cmd = [
        "gh", "api",
        "--method", method,
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2026-03-10",
        path,
    ]
    if payload is not None:
        cmd += ["--input", "-"]
    proc = run(cmd, input_text=json.dumps(payload) if payload is not None else None, check=False)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"GitHub API {method} {path} failed: {msg}")
    text = proc.stdout.strip()
    return json.loads(text) if text else None

def validate_payload(payload: dict) -> None:
    if payload.get("name") != RULESET_NAME:
        raise RuntimeError("Unexpected ruleset name.")
    if payload.get("target") != "branch" or payload.get("enforcement") != "active":
        raise RuntimeError("Ruleset must target branches and be active.")
    if payload.get("bypass_actors") not in ([], None):
        raise RuntimeError("Main protection must not contain an undocumented bypass actor.")
    refs = payload.get("conditions", {}).get("ref_name", {})
    if refs.get("include") != ["refs/heads/main"] or refs.get("exclude") != []:
        raise RuntimeError("Ruleset must target only refs/heads/main.")
    by_type = {rule.get("type"): rule for rule in payload.get("rules", [])}
    for required in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
        if required not in by_type:
            raise RuntimeError(f"Missing required rule: {required}")
    pr = by_type["pull_request"]["parameters"]
    if pr.get("required_approving_review_count") != 0:
        raise RuntimeError("Solo-owner repository is intentionally PR-required without mandatory second-person approval.")
    if pr.get("required_review_thread_resolution") is not True:
        raise RuntimeError("Review conversations must be resolved before merge.")
    status = by_type["required_status_checks"]["parameters"]
    actual = [row["context"] for row in status.get("required_status_checks", [])]
    if actual != EXPECTED_CHECKS:
        raise RuntimeError(f"Required check contract drifted: {actual!r}")
    if status.get("strict_required_status_checks_policy") is not True:
        raise RuntimeError("Required checks must use strict/up-to-date mode.")

def verify_ruleset(repo: str, ruleset: dict) -> None:
    validate_payload(ruleset)
    if ruleset.get("enforcement") != "active":
        raise RuntimeError("GitHub ruleset is not active.")
    # Also ask GitHub which active rules actually apply to main. This avoids
    # trusting only the stored ruleset object when multiple rulesets coexist.
    active = gh_api(repo, f"/repos/{repo}/rules/branches/{DEFAULT_BRANCH}")
    active_types = {row.get("type") for row in (active or [])}
    for needed in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
        if needed not in active_types:
            raise RuntimeError(f"GitHub does not report active `{needed}` protection on main.")
    print("PASS: GitHub reports active main protection.")
    print("Required checks:")
    for check_name in EXPECTED_CHECKS:
        print(f"  - {check_name}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    payload = json.loads(RULESET_FILE.read_text(encoding="utf-8"))
    validate_payload(payload)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    auth = run(["gh", "auth", "status"], check=False)
    if auth.returncode != 0:
        print("BLOCKED: GitHub CLI is not authenticated. Run `gh auth login` locally.", file=sys.stderr)
        return 2

    repo_meta = gh_api(args.repo, f"/repos/{args.repo}")
    if repo_meta.get("default_branch") != DEFAULT_BRANCH:
        print(f"BLOCKED: expected default branch `{DEFAULT_BRANCH}`.", file=sys.stderr)
        return 2
    if not repo_meta.get("permissions", {}).get("admin"):
        print("BLOCKED: authenticated identity does not have repository admin permission.", file=sys.stderr)
        return 2

    rulesets = gh_api(args.repo, f"/repos/{args.repo}/rulesets?includes_parents=true")
    existing = next(
        (r for r in rulesets or [] if r.get("name") == RULESET_NAME and r.get("source_type") == "Repository"),
        None,
    )

    if args.verify_only:
        if not existing:
            print("BLOCKED: ClipKaro main protection ruleset does not exist.", file=sys.stderr)
            return 2
        full = gh_api(args.repo, f"/repos/{args.repo}/rulesets/{existing['id']}")
        verify_ruleset(args.repo, full)
        return 0

    try:
        if existing:
            result = gh_api(
                args.repo,
                f"/repos/{args.repo}/rulesets/{existing['id']}",
                method="PUT",
                payload=payload,
            )
            action = "updated"
        else:
            result = gh_api(
                args.repo,
                f"/repos/{args.repo}/rulesets",
                method="POST",
                payload=payload,
            )
            action = "created"
    except RuntimeError as exc:
        msg = str(exc)
        if "403" in msg or "404" in msg:
            print(
                "BLOCKED: GitHub rejected ruleset administration. The token/app needs "
                "Administration: write, and private-repository rulesets must be available "
                "on the repository's GitHub plan.",
                file=sys.stderr,
            )
        raise

    full = gh_api(args.repo, f"/repos/{args.repo}/rulesets/{result['id']}")
    verify_ruleset(args.repo, full)
    print(f"PASS: {RULESET_NAME!r} {action} as active ruleset id={result['id']}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

FIRST_GOVERNED_PR = int(os.getenv("GOVERNANCE_FIRST_PR", "24"))
CLOSING_PATTERN = re.compile(r"(?im)^\s*(?:closes|fixes|resolves)\s+#(\d+)\b")
BRANCH_PATTERN = re.compile(r"^agent/\d+-[a-z0-9][a-z0-9-]*$")
REQUIRED_SECTIONS = (
    "## Risk",
    "## Critical invariants",
    "## Validation",
    "## Database / migration / compatibility",
    "## Security / privacy / secrets",
    "## Rollout / rollback",
    "## Scope check",
)


def validate_pull_request(payload: dict) -> list[str]:
    pr = payload.get("pull_request") or {}
    number = int(pr.get("number") or payload.get("number") or 0)
    user = (pr.get("user") or {}).get("login") or ""
    body = str(pr.get("body") or "")
    head_ref = str((pr.get("head") or {}).get("ref") or "")

    if user in {"dependabot[bot]", "github-actions[bot]"}:
        return []
    if number and number < FIRST_GOVERNED_PR:
        return []

    errors: list[str] = []
    issue_match = CLOSING_PATTERN.search(body)
    if not issue_match:
        errors.append("PR body must contain a real `Closes #<issue>` / `Fixes` / `Resolves` tracking link.")
    elif int(issue_match.group(1)) <= 0:
        errors.append("Tracking issue number must be positive.")

    if not BRANCH_PATTERN.fullmatch(head_ref):
        errors.append("Branch must match `agent/<issue-number>-<short-slug>`.")

    for section in REQUIRED_SECTIONS:
        if section.lower() not in body.lower():
            errors.append(f"PR body is missing required section: {section}")

    if "Tested head SHA:" not in body:
        errors.append("PR Validation must include `Tested head SHA:` and be filled with the final green head before merge.")
    return errors


def main() -> int:
    event_path = os.getenv("GITHUB_EVENT_PATH", "").strip()
    if len(sys.argv) > 1:
        event_path = sys.argv[1]
    if not event_path:
        print("PR governance check requires GITHUB_EVENT_PATH or an explicit event JSON path.", file=sys.stderr)
        return 2
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    errors = validate_pull_request(payload)
    if errors:
        print("PR Governance failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    pr = payload.get("pull_request") or {}
    print(f"PR Governance passed for #{pr.get('number') or payload.get('number') or '?'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

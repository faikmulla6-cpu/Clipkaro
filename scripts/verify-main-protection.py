#!/usr/bin/env python3
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    "PR Governance",
    "Critical Backend Invariants",
    "Critical Frontend Contracts",
    "Backend CI",
    "Frontend CI",
]

def main() -> int:
    ruleset = json.loads((ROOT / ".github/main-protection-ruleset.json").read_text(encoding="utf-8"))
    by_type = {r["type"]: r for r in ruleset["rules"]}
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"] == {"include": ["refs/heads/main"], "exclude": []}
    assert {"deletion", "non_fast_forward", "pull_request", "required_status_checks"} <= set(by_type)
    status = by_type["required_status_checks"]["parameters"]
    assert status["strict_required_status_checks_policy"] is True
    assert [x["context"] for x in status["required_status_checks"]] == EXPECTED
    assert by_type["pull_request"]["parameters"]["required_review_thread_resolution"] is True

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert ci["jobs"]["backend"]["name"] == "Backend CI"
    assert ci["jobs"]["frontend"]["name"] == "Frontend CI"

    critical = yaml.safe_load((ROOT / ".github/workflows/critical-product-contracts.yml").read_text(encoding="utf-8"))
    assert critical["jobs"]["backend-critical"]["name"] == "Critical Backend Invariants"
    assert critical["jobs"]["frontend-critical"]["name"] == "Critical Frontend Contracts"

    governance = yaml.safe_load((ROOT / ".github/workflows/pr-governance.yml").read_text(encoding="utf-8"))
    assert governance["jobs"]["governance"]["name"] == "PR Governance"

    print("PASS: source-controlled main-protection contract is internally consistent.")
    print("Required checks: " + ", ".join(EXPECTED))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

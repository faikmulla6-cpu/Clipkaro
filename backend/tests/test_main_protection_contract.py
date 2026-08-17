from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CHECKS = [
    "PR Governance",
    "Critical Backend Invariants",
    "Critical Frontend Contracts",
    "Backend CI",
    "Frontend CI",
]

def test_main_ruleset_blocks_unsafe_updates_and_requires_pr_checks() -> None:
    payload = json.loads((ROOT / ".github/main-protection-ruleset.json").read_text(encoding="utf-8"))
    assert payload["name"] == "ClipKaro main protection"
    assert payload["target"] == "branch"
    assert payload["enforcement"] == "active"
    assert payload["bypass_actors"] == []
    assert payload["conditions"]["ref_name"] == {
        "include": ["refs/heads/main"],
        "exclude": [],
    }
    rules = {rule["type"]: rule for rule in payload["rules"]}
    assert "deletion" in rules
    assert "non_fast_forward" in rules
    assert "pull_request" in rules
    assert "required_status_checks" in rules

    pr = rules["pull_request"]["parameters"]
    assert pr["required_approving_review_count"] == 0
    assert pr["required_review_thread_resolution"] is True

    required = rules["required_status_checks"]["parameters"]
    assert required["strict_required_status_checks_policy"] is True
    assert required["do_not_enforce_on_create"] is False
    assert [item["context"] for item in required["required_status_checks"]] == EXPECTED_CHECKS

def test_required_check_names_are_unique_and_source_controlled() -> None:
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    critical = yaml.safe_load(
        (ROOT / ".github/workflows/critical-product-contracts.yml").read_text(encoding="utf-8")
    )
    governance = yaml.safe_load((ROOT / ".github/workflows/pr-governance.yml").read_text(encoding="utf-8"))

    actual = [
        governance["jobs"]["governance"]["name"],
        critical["jobs"]["backend-critical"]["name"],
        critical["jobs"]["frontend-critical"]["name"],
        ci["jobs"]["backend"]["name"],
        ci["jobs"]["frontend"]["name"],
    ]
    assert actual == EXPECTED_CHECKS
    assert len(actual) == len(set(actual))

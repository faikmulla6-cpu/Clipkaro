from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_issue_first_templates_and_pr_template_exist() -> None:
    required = [
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_or_hardening.yml",
        ".github/ISSUE_TEMPLATE/qa_release.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/pull_request_template.md",
        "CONTRIBUTING.md",
    ]
    for path in required:
        assert (ROOT / path).exists(), f"GitHub process contract missing {path}"

    pr_template = _read(".github/pull_request_template.md")
    for marker in (
        "Closes #",
        "## Risk",
        "### Critical invariants touched",
        "## Validation",
        "Tested head SHA:",
        "## Rollout / rollback",
        "Merge will use the exact final head SHA",
    ):
        assert marker in pr_template


def test_normal_ci_is_least_privilege_and_does_not_duplicate_agent_push_runs() -> None:
    ci = _read(".github/workflows/ci.yml")
    assert "permissions:\n  contents: read" in ci
    assert "concurrency:" in ci
    assert "cancel-in-progress: true" in ci
    assert "workflow_dispatch:" in ci
    assert '"agent/**"' not in ci
    assert "persist-credentials: false" in ci


def test_critical_product_contracts_name_money_security_and_integrity_tests() -> None:
    workflow = _read(".github/workflows/critical-product-contracts.yml")
    for test_file in (
        "tests/test_api.py",
        "tests/test_subscription_lifecycle.py",
        "tests/test_sqlite_concurrency.py",
        "tests/test_email_verification.py",
        "tests/test_security_foundation.py",
        "tests/test_legal_privacy.py",
    ):
        assert test_file in workflow

    for contract in (
        "check:billing-lifecycle",
        "check:email-verification",
        "check:security-foundation",
        "check:legal-privacy",
    ):
        assert contract in workflow

    assert "permissions:\n  contents: read" in workflow
    assert "Critical Backend Invariants" in workflow
    assert "Critical Frontend Contracts" in workflow


def test_pr_governance_uses_trusted_base_and_issue_first_cutover() -> None:
    workflow = _read(".github/workflows/pr-governance.yml")
    script = _read("scripts/check_pr_governance.py")
    assert "pull_request_target:" in workflow
    assert "github.event.pull_request.base.sha" in workflow
    assert "persist-credentials: false" in workflow
    assert 'GOVERNANCE_FIRST_PR: "24"' in workflow
    assert "FIRST_GOVERNED_PR" in script
    assert "Closes #<issue>" in script
    assert "agent/<issue-number>-<short-slug>" in script
    compile(script, "scripts/check_pr_governance.py", "exec")


def test_contributing_requires_issue_branch_pr_history_and_exact_sha_merge() -> None:
    contributing = _read("CONTRIBUTING.md")
    for phrase in (
        "Every non-trivial change starts from a GitHub issue",
        "agent/<issue-number>-<short-slug>",
        "Commit in logical checkpoints",
        "merge commit that preserves the PR's logical checkpoint commits",
        "Open a draft PR early",
        "Critical Product Contracts",
        "Merge the exact tested SHA",
        "require a pull request before merging",
    ):
        assert phrase in contributing

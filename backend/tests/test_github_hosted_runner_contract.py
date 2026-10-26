from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

MIGRATED = (
    "ci.yml",
    "critical-product-contracts.yml",
    "pr-governance.yml",
    "asr-stress.yml",
    "landscape-export-qa.yml",
    "fresh-launch-qa.yml",
)


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_all_supported_jobs_use_ephemeral_github_hosted_ubuntu() -> None:
    for name in MIGRATED:
        content = read(name)
        assert "runs-on: ubuntu-24.04" in content, name
        assert "runs-on: [self-hosted" not in content, name
        if name != "pr-governance.yml":
            assert "bash scripts/check-github-hosted-runner.sh --profile" in content, name
        else:
            assert "Verify GitHub-hosted governance runner" in content, name


def test_runner_bootstrap_is_explicit_and_version_pinned() -> None:
    for name in MIGRATED:
        content = read(name)
        assert "actions/setup-python@v5" in content, name
        assert 'python-version: "3.12"' in content, name
    for name in ("ci.yml", "critical-product-contracts.yml", "fresh-launch-qa.yml"):
        content = read(name)
        assert "actions/setup-node@v4" in content, name
        assert 'node-version: "20"' in content, name
    for name in ("ci.yml", "critical-product-contracts.yml", "fresh-launch-qa.yml"):
        assert "faketime" in read(name), name


def test_checkout_credentials_never_persist_in_ci() -> None:
    for filename in MIGRATED:
        content = read(filename)
        assert "persist-credentials: false" in content, filename


def test_pr_security_boundary_remains_fail_closed() -> None:
    for filename in ("ci.yml", "critical-product-contracts.yml", "asr-stress.yml", "landscape-export-qa.yml", "fresh-launch-qa.yml"):
        assert "github.event.pull_request.head.repo.full_name == github.repository" in read(filename), filename
    governance = read("pr-governance.yml")
    assert "pull_request_target:" in governance
    assert "github.event.pull_request.base.sha" in governance
    assert "github.event.pull_request.head.repo.full_name != github.repository" in governance


def test_heavy_qualification_retains_real_resource_gates() -> None:
    helper = (ROOT / "scripts" / "check-github-hosted-runner.sh").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "GITHUB_HOSTED_RUNNERS.md").read_text(encoding="utf-8")
    assert "25 GiB" in helper
    assert "7400 MiB" in helper
    assert "python3.12" in helper
    assert "docker info" in helper
    assert "25 GiB" in docs
    assert "private" in docs.lower()


def test_backend_virtualenv_stays_isolated() -> None:
    for filename in ("ci.yml", "critical-product-contracts.yml", "fresh-launch-qa.yml", "asr-stress.yml", "landscape-export-qa.yml"):
        content = read(filename)
        assert "python3.12 -m venv .venv-ci" in content, filename
        assert 'echo "$PWD/.venv-ci/bin" >> "$GITHUB_PATH"' in content, filename

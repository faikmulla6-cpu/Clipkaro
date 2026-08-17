from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REQUIRED_RUNNER = "runs-on: [self-hosted, linux, x64, clipkaro-qa]"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_workflows_use_zero_cost_self_hosted_runner() -> None:
    names = {
        "ci.yml",
        "critical-product-contracts.yml",
        "pr-governance.yml",
        "asr-stress.yml",
        "landscape-export-qa.yml",
        "fresh-launch-qa.yml",
    }
    for name in names:
        text = _read(WORKFLOWS / name)
        assert "runs-on: ubuntu-latest" not in text, name
        assert REQUIRED_RUNNER in text, name


def test_persistent_runner_jobs_do_not_mutate_host_with_apt() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        text = _read(workflow)
        assert "apt-get" not in text, workflow.name
        assert "sudo apt" not in text, workflow.name


def test_checkout_does_not_persist_github_credentials() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        text = _read(workflow)
        if "actions/checkout@" in text:
            assert "persist-credentials: false" in text, workflow.name


def test_pull_request_jobs_refuse_fork_execution() -> None:
    for name in (
        "ci.yml",
        "critical-product-contracts.yml",
        "asr-stress.yml",
        "landscape-export-qa.yml",
        "fresh-launch-qa.yml",
    ):
        text = _read(WORKFLOWS / name)
        assert "github.event.pull_request.head.repo.full_name == github.repository" in text, name

    governance = _read(WORKFLOWS / "pr-governance.yml")
    assert "github.event.pull_request.head.repo.full_name == github.repository" in governance
    assert "pull_request_target:" in governance
    assert "github.event.pull_request.base.sha" in governance


def test_runner_preflight_and_docs_are_source_controlled() -> None:
    script = _read(ROOT / "scripts" / "check-self-hosted-runner.sh")
    docs = _read(ROOT / "docs" / "SELF_HOSTED_RUNNER.md")
    assert "Python 3.12" in script or '"3.12"' in script
    assert "Node.js 20" in script
    assert "docker compose version" in script
    assert "Do not run the GitHub runner service as root" in script
    assert "clipkaro-qa" in docs
    assert "8 GB-class RAM hard minimum" in docs
    assert "25 GiB free disk hard minimum" in docs


def test_backend_jobs_use_isolated_virtualenv_contract() -> None:
    for name in (
        "ci.yml",
        "critical-product-contracts.yml",
        "asr-stress.yml",
        "landscape-export-qa.yml",
        "fresh-launch-qa.yml",
    ):
        text = _read(WORKFLOWS / name)
        assert "python3.12 -m venv .venv-ci" in text, name
        assert 'echo "$PWD/.venv-ci/bin" >> "$GITHUB_PATH"' in text, name

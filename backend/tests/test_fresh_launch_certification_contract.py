from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_launch_qa_report.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("clipkaro_launch_qa", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _green_inputs(module):
    checks = {name: "success" for name in module.MANDATORY_CHECKS}
    identity = {
        "git_available": True,
        "sha_matches_checkout": True,
        "tracked_source_unchanged_before_evidence": True,
        "version_parity": True,
        "expected_version_matches": True,
    }
    preflight = {"ready": True, "blockers": []}
    pytest_data = {"available": True, "tests": 200, "failures": 0, "errors": 0, "skipped": 0}
    npm_data = {"available": True, "high": 0, "critical": 0}
    docker = {
        "images": {
            name: {"image_id": f"sha256:{name}", "repo_digest_or_id": f"sha256:{name}", "os": "linux", "architecture": "amd64"}
            for name in ("api", "worker", "frontend")
        }
    }
    workflow = {"run_id": "123", "repository": "faikmulla/ClipkaroAI"}
    return checks, identity, preflight, pytest_data, npm_data, docker, workflow


def test_full_green_contract_is_the_only_certifiable_state() -> None:
    module = _load_module()
    checks, identity, preflight, pytest_data, npm_data, docker, workflow = _green_inputs(module)
    decision, blockers, failures = module._certification_analysis(
        identity=identity,
        checks=checks,
        execution_preflight=preflight,
        pytest_data=pytest_data,
        npm_data=npm_data,
        docker_images=docker,
        workflow=workflow,
    )
    assert decision == "CERTIFIED"
    assert blockers == []
    assert failures == []


def test_missing_mandatory_check_is_blocked_not_certified() -> None:
    module = _load_module()
    checks, identity, preflight, pytest_data, npm_data, docker, workflow = _green_inputs(module)
    checks.pop("backend_worker_image")
    decision, blockers, _ = module._certification_analysis(
        identity=identity,
        checks=checks,
        execution_preflight=preflight,
        pytest_data=pytest_data,
        npm_data=npm_data,
        docker_images=docker,
        workflow=workflow,
    )
    assert decision == "BLOCKED"
    assert any("mandatory check outcomes missing" in item for item in blockers)


def test_red_check_or_high_audit_cannot_certify() -> None:
    module = _load_module()
    checks, identity, preflight, pytest_data, npm_data, docker, workflow = _green_inputs(module)
    checks["frontend_build"] = "failure"
    decision, _, failures = module._certification_analysis(
        identity=identity,
        checks=checks,
        execution_preflight=preflight,
        pytest_data=pytest_data,
        npm_data=npm_data,
        docker_images=docker,
        workflow=workflow,
    )
    assert decision == "FAIL"
    assert any("frontend_build" in item for item in failures)

    checks["frontend_build"] = "success"
    npm_data["high"] = 1
    decision, _, failures = module._certification_analysis(
        identity=identity,
        checks=checks,
        execution_preflight=preflight,
        pytest_data=pytest_data,
        npm_data=npm_data,
        docker_images=docker,
        workflow=workflow,
    )
    assert decision == "FAIL"
    assert any("high/critical" in item for item in failures)


def test_check_parser_rejects_duplicates_and_unknown_outcomes() -> None:
    module = _load_module()
    try:
        module._parse_checks(["backend_tests=success", "backend_tests=success"])
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate mandatory outcomes must fail")
    try:
        module._parse_checks(["backend_tests=maybe"])
    except ValueError:
        pass
    else:
        raise AssertionError("unknown outcome must fail")


def test_evidence_digest_detects_mutation() -> None:
    module = _load_module()
    payload = {"schema": "clipkaro.launch-qa.v2", "decision": "CERTIFIED", "checks": {"x": "success"}}
    digest = module._canonical_digest(payload)
    payload["evidence_sha256"] = digest
    assert module._canonical_digest(payload) == digest
    payload["decision"] = "FAIL"
    assert module._canonical_digest(payload) != digest


def test_fresh_launch_workflow_supplies_every_mandatory_check_and_artifact() -> None:
    module = _load_module()
    workflow = (ROOT / ".github" / "workflows" / "fresh-launch-qa.yml").read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in workflow
    assert "actions/setup-python@v5" in workflow
    assert "actions/setup-node@v4" in workflow
    assert "check_fresh_launch_execution_environment.py" in workflow
    assert "test -z \"$(git status --porcelain)\"" in workflow
    assert "docker-images.json" in workflow
    assert "launch-qa/QA_REPORT.md" in workflow
    assert "generate_launch_qa_report.py enforce" in workflow
    for name in module.MANDATORY_CHECKS:
        assert f"--check {name}=" in workflow, name

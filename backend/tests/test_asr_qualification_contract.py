from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from app.services.asr_qualification import threshold_contract, threshold_contract_sha256


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_script(name: str):
    path = BACKEND / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"clipkaro_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_controlled_threshold_lock_matches_benchmark_exactly() -> None:
    frozen = json.loads((BACKEND / "asr-threshold-lock.json").read_text(encoding="utf-8"))
    assert frozen["contract"] == threshold_contract()
    assert frozen["threshold_sha256"] == threshold_contract_sha256()
    encoded = json.dumps(frozen["contract"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == frozen["threshold_sha256"]


def test_launch_thresholds_remain_the_locked_values() -> None:
    contract = threshold_contract()
    assert contract["required_language_families"] == ["hi", "mr", "hinglish"]
    assert contract["minimum_qualification_cases_per_language"] == 2
    assert contract["minimum_language_match_rate"] == 0.80
    assert contract["minimum_timestamp_valid_rate"] == 0.95
    scenarios = {row["name"]: row for row in contract["scenarios"]}
    assert scenarios["clean"]["max_p90_wer"] == 0.28
    assert scenarios["clean"]["max_p90_cer"] == 0.18
    assert scenarios["clean"]["max_p95_rtf"] == 1.50
    assert scenarios["street_noise"]["max_p90_wer"] == 0.50
    assert scenarios["street_noise"]["max_p90_cer"] == 0.32
    assert scenarios["street_noise"]["max_p95_rtf"] == 1.80
    assert contract["negative_controls"] == ["silence", "noise_only", "tone_only"]


def test_real_asr_workflow_is_exact_sha_threshold_locked_and_evidence_driven() -> None:
    workflow = _read(".github/workflows/asr-stress.yml")
    required = (
        "runs-on: [self-hosted, linux, x64, clipkaro-qa]",
        "TESTED_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
        "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
        'test "$(git rev-parse HEAD)" = "$TESTED_SHA"',
        "Lock ASR thresholds before inference",
        "threshold-lock-before.json",
        "Lock ASR thresholds after inference",
        "threshold-lock-after.json",
        "check_asr_execution_environment.py",
        "finalize_asr_qualification.py",
        "asr-qualification-evidence.json",
        "asr-qualification-summary.md",
        "Enforce immutable real-ASR verdict",
    )
    for marker in required:
        assert marker in workflow


def test_finalizer_classifies_missing_execution_as_blocked_and_red_metrics_as_fail(tmp_path: Path) -> None:
    finalizer = _load_script("finalize_asr_qualification.py")
    identity = {"git_sha": "a" * 40, "exact_sha_match": True, "clean": True}
    threshold = {"unchanged_during_run": True, "current_sha256": "locked-threshold"}
    ready = {"ready": True, "blockers": []}
    resources = {name: {"exit_status": 0} for name in ("core", "cafe", "fan", "hinted", "concurrency")}
    hardware = tmp_path / "hardware.txt"
    hardware.write_text("ok", encoding="utf-8")

    decision, blockers, _ = finalizer._decision(
        identity=identity, threshold=threshold, preflight=ready,
        core=None, cafe=None, fan=None, hinted=None, concurrency=None,
        hardware=hardware, resources=resources,
    )
    assert decision == "BLOCKED"
    assert any("missing core qualification report" in item for item in blockers)

    core = {"production_ready": False, "threshold_sha256": "locked-threshold"}
    sweep = {"selected_scenarios_passed": True, "threshold_sha256": "locked-threshold"}
    concurrency = {"passed": True, "threshold_sha256": "locked-threshold"}
    decision, _, failures = finalizer._decision(
        identity=identity, threshold=threshold, preflight=ready,
        core=core, cafe=sweep, fan=sweep, hinted=sweep, concurrency=concurrency,
        hardware=hardware, resources=resources,
    )
    assert decision == "FAIL"
    assert "core Hindi/Marathi/Hinglish qualification failed" in failures


def test_qualification_support_scripts_compile() -> None:
    for name in (
        "write_asr_threshold_lock.py",
        "check_asr_execution_environment.py",
        "finalize_asr_qualification.py",
    ):
        path = BACKEND / "scripts" / name
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_qualification_harness_records_api_candidate_without_changing_thresholds() -> None:
    benchmark = _load_script("asr_stress_benchmark.py")
    source = _read("backend/scripts/asr_stress_benchmark.py")
    assert "--asr-mode" in source
    assert '"asr_candidate"' in source
    assert "settings.groq_asr_model" in source

from __future__ import annotations

import json
from pathlib import Path

from app.services.landscape_qualification import (
    CASE_COUNT,
    CLIP_SECONDS,
    EXPORTS_REQUIRED,
    MIN_RELIABLY_SCORED_CASES,
    POLICIES,
    SAMPLES_PER_CASE,
    report_is_complete,
    threshold_contract,
    threshold_contract_sha256,
)


ROOT = Path(__file__).resolve().parents[2]


def _green_report() -> dict:
    cases = []
    exports = []
    for index in range(CASE_COUNT):
        case_id = f"case-{index + 1}"
        cases.append(
            {
                "id": case_id,
                "scored": True,
                "sample_count": SAMPLES_PER_CASE,
                "multi_face_samples": 2 if index in {2, 7} else 0,
                "detection": {"detection_coverage": 1.0},
                "default": {"passed": True},
                "manual": {"passed": True},
                "dynamic": {"passed": True},
                "case_sha256": "a" * 64,
            }
        )
        for policy in POLICIES:
            exports.append(
                {
                    "case_id": case_id,
                    "policy": policy,
                    "ok": True,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "path": f"exports/{case_id}-{policy}.mp4",
                    "sha256": "b" * 64,
                }
            )
    return {
        "case_count": CASE_COUNT,
        "policies_per_case": len(POLICIES),
        "export_count": EXPORTS_REQUIRED,
        "successful_export_count": EXPORTS_REQUIRED,
        "threshold_lock": {"threshold_sha256": threshold_contract_sha256()},
        "cases": cases,
        "exports": exports,
        "summary": {
            "evidence_valid": True,
            "scored_cases": CASE_COUNT,
            "verdict": "manual_focus_sufficient_for_now",
            "default_case_pass_rate": 1.0,
            "manual_case_pass_rate": 1.0,
            "dynamic_case_pass_rate": 1.0,
            "dynamic_only_rescue_rate": 0.0,
            "multi_face_sample_rate": 0.0333,
        },
    }


def test_landscape_threshold_lock_is_frozen_and_self_consistent() -> None:
    contract = threshold_contract()
    assert contract["case_count"] == 10
    assert contract["policies"] == ["center", "manual", "dynamic"]
    assert contract["exports_required"] == 30
    assert contract["clip_seconds"] == 8.0
    assert contract["samples_per_case"] == 12
    assert len(contract["sources"]) == 5
    assert {item["filename"] for item in contract["sources"]} == {
        "Interview_with_Janno_Loide.webm",
        "Rwicinterview2.webm",
        "Rwicinterview3.webm",
        "Erik_Gudbranson_interview.webm",
        "Friedel_Wikipedia_Public_Policy_Initiative_interview_clip.webm",
    }
    assert contract["detection"]["minimum_reliably_scored_cases"] == 8
    assert contract["case_score"]["minimum_frame_pass_rate"] == 0.90
    payload = json.loads((ROOT / "backend" / "landscape-threshold-lock.json").read_text(encoding="utf-8"))
    assert payload["threshold_sha256"] == threshold_contract_sha256()


def test_complete_10_by_3_real_export_matrix_is_qualification_complete() -> None:
    complete, failures = report_is_complete(_green_report())
    assert complete is True
    assert failures == []


def test_missing_export_or_audio_codec_fails_closed() -> None:
    report = _green_report()
    report["exports"].pop()
    report["export_count"] = 29
    report["successful_export_count"] = 29
    complete, failures = report_is_complete(report)
    assert complete is False
    assert any("30" in item or "matrix" in item for item in failures)

    report = _green_report()
    report["exports"][0]["audio_codec"] = "vorbis"
    complete, failures = report_is_complete(report)
    assert complete is False
    assert any("AAC" in item for item in failures)


def test_inconclusive_face_evidence_cannot_become_execution_pass() -> None:
    report = _green_report()
    report["summary"]["scored_cases"] = MIN_RELIABLY_SCORED_CASES - 1
    report["summary"]["evidence_valid"] = False
    report["summary"]["verdict"] = "inconclusive"
    complete, failures = report_is_complete(report)
    assert complete is False
    assert any("face-scored" in item for item in failures)


def test_runner_supports_real_media_cache_without_weakening_locked_matrix() -> None:
    script = (ROOT / "backend" / "scripts" / "landscape_export_qa.py").read_text(encoding="utf-8")
    assert "--source-dir" in script
    assert "_acquire_source" in script
    assert "CASE_COUNT" in script
    assert "CLIP_SECONDS" in script
    assert "SAMPLES_PER_CASE" in script
    assert "OUTPUT_AUDIO_CODEC" in script
    assert "threshold_contract_sha256()" in script


def test_workflow_uses_exact_sha_self_hosted_runner_and_immutable_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "landscape-export-qa.yml").read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in workflow
    assert "TESTED_SHA:" in workflow
    assert "Checkout exact candidate SHA" in workflow
    assert 'test "$(git rev-parse HEAD)" = "$TESTED_SHA"' in workflow
    assert "run-real-landscape-qualification.sh" in workflow
    assert "LANDSCAPE_SOURCE_DIR: ${{ vars.LANDSCAPE_SOURCE_DIR }}" in workflow
    assert "landscape-qualification-evidence.json" in workflow
    assert "threshold-lock-before.json" in workflow
    assert "threshold-lock-after.json" in workflow


def test_one_command_runner_requires_git_identity_and_never_changes_thresholds() -> None:
    runner = (ROOT / "scripts" / "run-real-landscape-qualification.sh").read_text(encoding="utf-8")
    assert "git -C \"$ROOT\" rev-parse HEAD" in runner
    assert "TESTED_SHA" in runner
    assert "write_landscape_threshold_lock.py" in runner
    assert "finalize_landscape_qualification.py" in runner
    assert "landscape_export_qa.py" in runner
    assert "landscape-threshold-lock.json" not in runner  # runner records; it never rewrites the source lock


def test_locked_defaults_match_the_30_export_request() -> None:
    assert CASE_COUNT == 10
    assert POLICIES == ("center", "manual", "dynamic")
    assert EXPORTS_REQUIRED == 30
    assert CLIP_SECONDS == 8.0
    assert SAMPLES_PER_CASE == 12

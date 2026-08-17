from __future__ import annotations

from pathlib import Path

import pytest

from app.services.landscape_export_qa import (
    FaceBox,
    FaceObservation,
    best_static_focus,
    crop_window,
    desired_focus_for_face,
    score_dynamic_focus,
    score_focus,
    summarize_landscape_cases,
    visible_source_width,
)


def _observation(time: float, center_x: float, *, faces: int = 1) -> FaceObservation:
    return FaceObservation(
        time=time,
        frame_width=1280,
        frame_height=720,
        primary=FaceBox(x=center_x - 70, y=170, width=140, height=180),
        face_count=faces,
    )


def test_portrait_export_keeps_only_narrow_landscape_slice() -> None:
    portrait = visible_source_width(1280, 720, "9:16")
    square = visible_source_width(1280, 720, "1:1")
    feed = visible_source_width(1280, 720, "4:5")
    assert portrait == pytest.approx(405)
    assert portrait < feed < square
    left, right = crop_window(1280, 720, 50, "9:16")
    assert right - left == pytest.approx(405)
    assert (left + right) / 2 == pytest.approx(640)


def test_off_center_solo_is_rescued_by_one_manual_focus() -> None:
    rows = [_observation(time, 285) for time in range(8)]
    centered = score_focus(rows, lambda _: 50)
    manual_focus, manual = best_static_focus(rows)
    assert centered.passed is False
    assert manual.passed is True
    assert manual_focus < 20
    assert desired_focus_for_face(rows[0]) == pytest.approx(manual_focus, abs=2.0)


def test_large_cross_frame_motion_needs_time_varying_focus() -> None:
    rows = [_observation(float(index), 250 + index * (780 / 7)) for index in range(8)]
    _, manual = best_static_focus(rows)
    keyframes, dynamic = score_dynamic_focus(rows, duration=7)
    assert manual.passed is False
    assert dynamic.passed is True
    assert len(keyframes) >= 4
    assert keyframes[0]["focus_x"] < keyframes[-1]["focus_x"]


def test_small_seated_drift_remains_manual_focus_friendly() -> None:
    rows = [_observation(float(index), 370 + index * 20) for index in range(8)]
    _, manual = best_static_focus(rows)
    assert manual.passed is True


def test_abrupt_left_to_right_speaker_handoff_is_not_falsely_marked_solved() -> None:
    rows = [
        *[_observation(float(index), 285) for index in range(4)],
        *[_observation(float(index), 995) for index in range(4, 8)],
    ]
    _, manual = best_static_focus(rows)
    _, dynamic = score_dynamic_focus(rows, duration=7)
    assert manual.passed is False
    # crop_tracking intentionally caps horizontal movement at 18 focus points/s.
    # Without scene-cut semantics, a sudden opposite-side speaker switch cannot
    # be called solved merely because time-varying keyframes exist.
    assert dynamic.passed is False


def _case(manual: bool, dynamic: bool, default: bool = False, multi: int = 0) -> dict:
    return {
        "scored": True,
        "sample_count": 10,
        "multi_face_samples": multi,
        "default": {"passed": default},
        "manual": {"passed": manual},
        "dynamic": {"passed": dynamic},
    }


def test_product_verdict_allows_manual_focus_when_dynamic_rescues_are_rare() -> None:
    rows = [_case(True, True) for _ in range(9)] + [_case(False, True)]
    summary = summarize_landscape_cases(rows)
    assert summary["evidence_valid"] is True
    assert summary["manual_focus_sufficient_for_now"] is True
    assert summary["verdict"] == "manual_focus_sufficient_for_now"
    assert summary["manual_case_pass_rate"] == pytest.approx(0.9)
    assert summary["dynamic_only_rescue_rate"] == pytest.approx(0.1)


def test_product_verdict_marks_tracking_critical_when_static_manual_fails_common_cases() -> None:
    rows = [_case(True, True) for _ in range(7)] + [_case(False, True) for _ in range(3)]
    summary = summarize_landscape_cases(rows)
    assert summary["evidence_valid"] is True
    assert summary["manual_focus_sufficient_for_now"] is False
    assert summary["advanced_reframe_required"] is True
    assert summary["verdict"] == "automatic_face_tracking_is_critical"
    assert summary["dynamic_only_rescue_rate"] == pytest.approx(0.3)


def test_product_verdict_calls_dynamic_failure_real_reframe_evidence() -> None:
    # Mirrors the adversarial 30-export fallback class result: seven layouts are
    # static-manual friendly, one is rescued only by motion tracking, and two
    # abrupt opposite-side handoffs defeat the current smoothed dynamic policy.
    rows = [
        *[_case(True, True) for _ in range(7)],
        _case(False, True),
        _case(False, False),
        _case(False, False),
    ]
    summary = summarize_landscape_cases(rows)
    assert summary["evidence_valid"] is True
    assert summary["manual_case_pass_rate"] == pytest.approx(0.7)
    assert summary["dynamic_case_pass_rate"] == pytest.approx(0.8)
    assert summary["manual_focus_sufficient_for_now"] is False
    assert summary["advanced_reframe_required"] is True
    assert summary["verdict"] == "automatic_reframe_needs_scene_cut_or_speaker_logic"


def test_manual_can_still_be_sufficient_when_dynamic_tracker_itself_is_unqualified() -> None:
    rows = [
        *[_case(True, True) for _ in range(8)],
        _case(True, False),
        _case(True, False),
    ]
    summary = summarize_landscape_cases(rows)
    assert summary["evidence_valid"] is True
    assert summary["manual_focus_sufficient_for_now"] is True
    assert summary["advanced_reframe_required"] is False
    assert summary["verdict"] == "manual_focus_sufficient_but_auto_tracking_not_qualified"


def test_too_few_reliable_face_cases_stays_inconclusive() -> None:
    rows = [_case(True, True) for _ in range(7)]
    summary = summarize_landscape_cases(rows)
    assert summary["evidence_valid"] is False
    assert summary["verdict"] == "inconclusive"


def test_multi_face_rate_flags_active_speaker_followup_without_rewriting_verdict() -> None:
    rows = [_case(True, True, multi=3) for _ in range(10)]
    summary = summarize_landscape_cases(rows)
    assert summary["manual_focus_sufficient_for_now"] is True
    assert summary["speaker_tracking_followup_recommended"] is True
    assert summary["multi_face_sample_rate"] == pytest.approx(0.3)


def test_standalone_landscape_qa_runner_compiles() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    script = backend_root / "scripts" / "landscape_export_qa.py"
    compile(script.read_text(encoding="utf-8"), str(script), "exec")

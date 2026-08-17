from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from statistics import mean
from typing import Callable, Iterable

from .crop_tracking import smooth_crop_keyframes
from .landscape_qualification import (
    CASE_MIN_AVERAGE_VISIBILITY,
    CASE_MIN_P10_VISIBILITY,
    CASE_MIN_PASS_RATE,
    DYNAMIC_POLICY_MIN_CASE_PASS_RATE,
    FRAME_MAX_CENTER_ERROR,
    FRAME_MIN_VISIBILITY,
    MANUAL_SUFFICIENT_MAX_DYNAMIC_RESCUE_RATE,
    MANUAL_SUFFICIENT_MIN_CASE_PASS_RATE,
    MIN_RELIABLY_SCORED_CASES,
    MULTI_FACE_FOLLOWUP_RATE,
    TRACKING_CRITICAL_AT_DYNAMIC_RESCUE_RATE,
    TRACKING_CRITICAL_BELOW_MANUAL_PASS_RATE,
)


@dataclass(frozen=True)
class FaceBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2


@dataclass(frozen=True)
class FaceObservation:
    time: float
    frame_width: float
    frame_height: float
    primary: FaceBox
    face_count: int = 1


@dataclass(frozen=True)
class FocusScore:
    sample_count: int
    pass_rate: float
    average_visibility: float
    p10_visibility: float
    average_center_error: float
    worst_center_error: float
    passed: bool

    def as_dict(self) -> dict:
        return asdict(self)


def parse_aspect_ratio(value: str) -> float:
    left, right = str(value).split(":", 1)
    width, height = float(left), float(right)
    if width <= 0 or height <= 0:
        raise ValueError("Aspect-ratio dimensions must be positive.")
    return width / height


def visible_source_width(frame_width: float, frame_height: float, aspect_ratio: str = "9:16") -> float:
    """Return the horizontal source span retained after ClipKaro's scale+crop.

    render_short() scales the source until the target frame is filled, then
    performs a horizontal crop for normal landscape podcast input. This helper
    mirrors that geometry without invoking FFmpeg so framing policy can be
    scored deterministically.
    """
    target = parse_aspect_ratio(aspect_ratio)
    source = frame_width / frame_height
    if source <= target:
        return frame_width
    return frame_height * target


def crop_window(frame_width: float, frame_height: float, focus_x: float,
                aspect_ratio: str = "9:16") -> tuple[float, float]:
    visible = visible_source_width(frame_width, frame_height, aspect_ratio)
    travel = max(0.0, frame_width - visible)
    focus = max(0.0, min(float(focus_x), 100.0)) / 100.0
    left = travel * focus
    return left, left + visible


def desired_focus_for_face(observation: FaceObservation, aspect_ratio: str = "9:16") -> float:
    visible = visible_source_width(observation.frame_width, observation.frame_height, aspect_ratio)
    travel = observation.frame_width - visible
    if travel <= 0:
        return 50.0
    left = observation.primary.center_x - visible / 2
    return max(0.0, min(100.0, left / travel * 100.0))


def face_visibility(observation: FaceObservation, focus_x: float,
                    aspect_ratio: str = "9:16") -> tuple[float, float]:
    left, right = crop_window(observation.frame_width, observation.frame_height, focus_x, aspect_ratio)
    face_left = observation.primary.x
    face_right = observation.primary.x + observation.primary.width
    overlap = max(0.0, min(face_right, right) - max(face_left, left))
    visibility = overlap / max(1.0, observation.primary.width)
    crop_width = max(1.0, right - left)
    center_error = abs(observation.primary.center_x - (left + right) / 2) / crop_width
    return min(1.0, visibility), center_error


def percentile(values: Iterable[float], q: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return math.inf
    if len(rows) == 1:
        return rows[0]
    index = (len(rows) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    if lo == hi:
        return rows[lo]
    weight = index - lo
    return rows[lo] * (1 - weight) + rows[hi] * weight


def score_focus(observations: list[FaceObservation], focus_for: Callable[[FaceObservation], float],
                aspect_ratio: str = "9:16", min_visibility: float = FRAME_MIN_VISIBILITY,
                max_center_error: float = FRAME_MAX_CENTER_ERROR) -> FocusScore:
    if not observations:
        return FocusScore(0, 0.0, 0.0, 0.0, math.inf, math.inf, False)
    visibilities: list[float] = []
    center_errors: list[float] = []
    passes = 0
    for observation in observations:
        visibility, center_error = face_visibility(observation, focus_for(observation), aspect_ratio)
        visibilities.append(visibility)
        center_errors.append(center_error)
        if visibility >= min_visibility and center_error <= max_center_error:
            passes += 1
    pass_rate = passes / len(observations)
    average_visibility = mean(visibilities)
    p10_visibility = percentile(visibilities, 0.10)
    average_center_error = mean(center_errors)
    worst_center_error = max(center_errors)
    passed = (pass_rate >= CASE_MIN_PASS_RATE and average_visibility >= CASE_MIN_AVERAGE_VISIBILITY
              and p10_visibility >= CASE_MIN_P10_VISIBILITY)
    return FocusScore(
        sample_count=len(observations),
        pass_rate=round(pass_rate, 4),
        average_visibility=round(average_visibility, 4),
        p10_visibility=round(p10_visibility, 4),
        average_center_error=round(average_center_error, 4),
        worst_center_error=round(worst_center_error, 4),
        passed=passed,
    )


def best_static_focus(observations: list[FaceObservation], aspect_ratio: str = "9:16") -> tuple[float, FocusScore]:
    """Find the best single manual focus value available to today's editor."""
    if not observations:
        return 50.0, score_focus([], lambda _: 50.0, aspect_ratio)
    best_focus = 50.0
    best_score: FocusScore | None = None
    for focus in range(0, 101):
        current = score_focus(observations, lambda _observation, value=float(focus): value, aspect_ratio)
        rank = (
            current.passed,
            current.pass_rate,
            current.p10_visibility,
            current.average_visibility,
            -current.average_center_error,
            -abs(focus - 50),
        )
        if best_score is None:
            best_focus, best_score, best_rank = float(focus), current, rank
        elif rank > best_rank:
            best_focus, best_score, best_rank = float(focus), current, rank
    assert best_score is not None
    return best_focus, best_score


def dynamic_focus_keyframes(observations: list[FaceObservation], duration: float,
                            aspect_ratio: str = "9:16") -> list[dict[str, float]]:
    if not observations:
        return smooth_crop_keyframes([], duration, 50)
    raw: list[dict[str, float]] = []
    previous: float | None = None
    for observation in observations:
        focus = desired_focus_for_face(observation, aspect_ratio)
        # Keep the timeline compact while preserving meaningful speaker/camera movement.
        if previous is None or abs(focus - previous) >= 1.5 or not raw:
            raw.append({"time": max(0.0, min(float(observation.time), duration)), "focus_x": focus})
            previous = focus
    return smooth_crop_keyframes(raw, duration, 50)


def focus_at_time(keyframes: list[dict[str, float]], time_value: float) -> float:
    if not keyframes:
        return 50.0
    if time_value <= keyframes[0]["time"]:
        return float(keyframes[0]["focus_x"])
    for left, right in zip(keyframes, keyframes[1:]):
        if time_value <= right["time"]:
            span = max(0.001, right["time"] - left["time"])
            weight = (time_value - left["time"]) / span
            return float(left["focus_x"] + (right["focus_x"] - left["focus_x"]) * weight)
    return float(keyframes[-1]["focus_x"])


def score_dynamic_focus(observations: list[FaceObservation], duration: float,
                        aspect_ratio: str = "9:16") -> tuple[list[dict[str, float]], FocusScore]:
    keyframes = dynamic_focus_keyframes(observations, duration, aspect_ratio)
    return keyframes, score_focus(
        observations,
        lambda observation: focus_at_time(keyframes, observation.time),
        aspect_ratio,
    )


def summarize_landscape_cases(cases: list[dict]) -> dict:
    scored = [case for case in cases if case.get("scored")]
    if not scored:
        return {
            "verdict": "inconclusive",
            "reason": "no_scored_cases",
            "evidence_valid": False,
            "manual_focus_sufficient_for_now": False,
            "advanced_reframe_required": False,
        }
    default_passes = sum(bool(case["default"]["passed"]) for case in scored)
    manual_passes = sum(bool(case["manual"]["passed"]) for case in scored)
    dynamic_passes = sum(bool(case["dynamic"]["passed"]) for case in scored)
    dynamic_rescues = sum(
        not bool(case["manual"]["passed"]) and bool(case["dynamic"]["passed"])
        for case in scored
    )
    multi_face_samples = sum(int(case.get("multi_face_samples", 0)) for case in scored)
    samples = sum(int(case.get("sample_count", 0)) for case in scored)
    count = len(scored)
    default_rate = default_passes / count
    manual_rate = manual_passes / count
    dynamic_rate = dynamic_passes / count
    rescue_rate = dynamic_rescues / count
    multi_face_rate = multi_face_samples / max(1, samples)

    # Product decision rule. A weak dynamic result is itself valid evidence when
    # the exports and face measurements are complete: it means simple smoothed
    # face keyframes are not enough (for example, hard camera/speaker cuts may
    # require scene-boundary-aware snapping). Do not misclassify product failure
    # as benchmark infrastructure failure.
    if count < MIN_RELIABLY_SCORED_CASES:
        verdict = "inconclusive"
        sufficient = False
        advanced = False
        evidence_valid = False
        reason = "fewer_than_8_reliable_face_cases"
    elif (dynamic_rate < DYNAMIC_POLICY_MIN_CASE_PASS_RATE
          and manual_rate >= MANUAL_SUFFICIENT_MIN_CASE_PASS_RATE
          and rescue_rate < MANUAL_SUFFICIENT_MAX_DYNAMIC_RESCUE_RATE):
        verdict = "manual_focus_sufficient_but_auto_tracking_not_qualified"
        sufficient = True
        advanced = False
        evidence_valid = True
        reason = "manual_focus_is_reliable_but_smoothed_dynamic_tracking_needs_more_work"
    elif dynamic_rate < DYNAMIC_POLICY_MIN_CASE_PASS_RATE:
        verdict = "automatic_reframe_needs_scene_cut_or_speaker_logic"
        sufficient = False
        advanced = True
        evidence_valid = True
        reason = "time_varying_focus_also_failed_common_cases_so_face_tracking_alone_is_insufficient"
    elif (manual_rate < TRACKING_CRITICAL_BELOW_MANUAL_PASS_RATE
          or rescue_rate >= TRACKING_CRITICAL_AT_DYNAMIC_RESCUE_RATE):
        verdict = "automatic_face_tracking_is_critical"
        sufficient = False
        advanced = True
        evidence_valid = True
        reason = "single_manual_focus_cannot_hold_the_primary_face_reliably"
    elif (manual_rate >= MANUAL_SUFFICIENT_MIN_CASE_PASS_RATE
          and rescue_rate < MANUAL_SUFFICIENT_MAX_DYNAMIC_RESCUE_RATE):
        verdict = "manual_focus_sufficient_for_now"
        sufficient = True
        advanced = False
        evidence_valid = True
        reason = "single_manual_focus_handles_representative_landscape_cases"
    else:
        verdict = "manual_focus_sufficient_with_guardrails"
        sufficient = True
        advanced = False
        evidence_valid = True
        reason = "manual_focus_is_viable_but_moving_or_multi_face_clips_need_review"

    return {
        "verdict": verdict,
        "reason": reason,
        "evidence_valid": evidence_valid,
        "manual_focus_sufficient_for_now": sufficient,
        "advanced_reframe_required": advanced,
        "scored_cases": count,
        "default_case_pass_rate": round(default_rate, 4),
        "manual_case_pass_rate": round(manual_rate, 4),
        "dynamic_case_pass_rate": round(dynamic_rate, 4),
        "dynamic_only_rescue_rate": round(rescue_rate, 4),
        "multi_face_sample_rate": round(multi_face_rate, 4),
        "decision_thresholds": {
            "manual_sufficient_min_case_pass_rate": MANUAL_SUFFICIENT_MIN_CASE_PASS_RATE,
            "manual_sufficient_max_dynamic_rescue_rate": MANUAL_SUFFICIENT_MAX_DYNAMIC_RESCUE_RATE,
            "tracking_critical_below_manual_pass_rate": TRACKING_CRITICAL_BELOW_MANUAL_PASS_RATE,
            "tracking_critical_at_dynamic_rescue_rate": TRACKING_CRITICAL_AT_DYNAMIC_RESCUE_RATE,
            "dynamic_policy_min_case_pass_rate": DYNAMIC_POLICY_MIN_CASE_PASS_RATE,
        },
        "speaker_tracking_followup_recommended": multi_face_rate >= MULTI_FACE_FOLLOWUP_RATE,
        "multi_face_case_ids": [str(case.get("id")) for case in scored if int(case.get("multi_face_samples", 0)) > 0],
    }

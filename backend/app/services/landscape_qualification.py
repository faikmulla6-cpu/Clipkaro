from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = BACKEND_ROOT / "landscape-threshold-lock.json"

VALID_PRODUCT_VERDICTS = {
    "manual_focus_sufficient_for_now",
    "manual_focus_sufficient_with_guardrails",
    "manual_focus_sufficient_but_auto_tracking_not_qualified",
    "automatic_face_tracking_is_critical",
    "automatic_reframe_needs_scene_cut_or_speaker_logic",
}


def threshold_lock() -> dict[str, Any]:
    payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    contract = payload.get("contract")
    if not isinstance(contract, dict):
        raise RuntimeError("Landscape threshold lock is missing its contract.")
    encoded = json.dumps(
        contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != payload.get("threshold_sha256"):
        raise RuntimeError("Landscape threshold lock is internally inconsistent.")
    return payload


def threshold_contract() -> dict[str, Any]:
    return dict(threshold_lock()["contract"])


def threshold_contract_sha256() -> str:
    return str(threshold_lock()["threshold_sha256"])


CONTRACT = threshold_contract()
CONTRACT_VERSION = str(CONTRACT["contract_version"])
CASE_COUNT = int(CONTRACT["case_count"])
POLICIES = tuple(str(item) for item in CONTRACT["policies"])
EXPORTS_REQUIRED = int(CONTRACT["exports_required"])
CLIP_SECONDS = float(CONTRACT["clip_seconds"])
SAMPLES_PER_CASE = int(CONTRACT["samples_per_case"])
TARGET_ASPECT_RATIO = str(CONTRACT["target_aspect_ratio"])
SOURCE_WINDOW_FRACTIONS = tuple(float(item) for item in CONTRACT["source_window_fractions"])
SOURCE_SPECS = tuple(dict(item) for item in CONTRACT["sources"])

DETECTION_MIN_COVERAGE = float(CONTRACT["detection"]["minimum_coverage"])
DETECTION_MIN_OBSERVATIONS = int(CONTRACT["detection"]["minimum_observations"])
MIN_RELIABLY_SCORED_CASES = int(CONTRACT["detection"]["minimum_reliably_scored_cases"])

FRAME_MIN_VISIBILITY = float(CONTRACT["frame_score"]["minimum_face_visibility"])
FRAME_MAX_CENTER_ERROR = float(CONTRACT["frame_score"]["maximum_center_error"])
CASE_MIN_PASS_RATE = float(CONTRACT["case_score"]["minimum_frame_pass_rate"])
CASE_MIN_AVERAGE_VISIBILITY = float(CONTRACT["case_score"]["minimum_average_visibility"])
CASE_MIN_P10_VISIBILITY = float(CONTRACT["case_score"]["minimum_p10_visibility"])

MANUAL_SUFFICIENT_MIN_CASE_PASS_RATE = float(
    CONTRACT["decision"]["manual_sufficient_min_case_pass_rate"]
)
MANUAL_SUFFICIENT_MAX_DYNAMIC_RESCUE_RATE = float(
    CONTRACT["decision"]["manual_sufficient_max_dynamic_rescue_rate"]
)
TRACKING_CRITICAL_BELOW_MANUAL_PASS_RATE = float(
    CONTRACT["decision"]["tracking_critical_below_manual_pass_rate"]
)
TRACKING_CRITICAL_AT_DYNAMIC_RESCUE_RATE = float(
    CONTRACT["decision"]["tracking_critical_at_dynamic_rescue_rate"]
)
DYNAMIC_POLICY_MIN_CASE_PASS_RATE = float(
    CONTRACT["decision"]["dynamic_policy_min_case_pass_rate"]
)
MULTI_FACE_FOLLOWUP_RATE = float(CONTRACT["decision"]["multi_face_followup_rate"])

OUTPUT_VIDEO_CODEC = str(CONTRACT["output_validation"]["video_codec"])
OUTPUT_AUDIO_CODEC = str(CONTRACT["output_validation"]["audio_codec"])
OUTPUT_MIN_SIZE_BYTES = int(CONTRACT["output_validation"]["minimum_size_bytes"])
OUTPUT_DURATION_SLACK_SECONDS = float(
    CONTRACT["output_validation"]["minimum_duration_slack_seconds"]
)
OUTPUT_RESOLUTIONS = {
    str(name): tuple(int(v) for v in value)
    for name, value in CONTRACT["output_validation"]["resolutions"].items()
}


def report_is_complete(report: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Validate evidence completeness without reinterpreting the product verdict."""
    failures: list[str] = []
    if not isinstance(report, dict):
        return False, ["landscape report is missing"]

    if int(report.get("case_count") or 0) != CASE_COUNT:
        failures.append(f"expected {CASE_COUNT} cases")
    if int(report.get("policies_per_case") or 0) != len(POLICIES):
        failures.append(f"expected {len(POLICIES)} policies per case")
    if int(report.get("export_count") or 0) != EXPORTS_REQUIRED:
        failures.append(f"expected {EXPORTS_REQUIRED} exports")
    if int(report.get("successful_export_count") or 0) != EXPORTS_REQUIRED:
        failures.append(f"expected {EXPORTS_REQUIRED} validated exports")

    cases = report.get("cases") or []
    if len(cases) != CASE_COUNT:
        failures.append("case evidence count does not match contract")
    exports = report.get("exports") or []
    if len(exports) != EXPORTS_REQUIRED:
        failures.append("export evidence count does not match contract")

    expected_pairs = {(str(case.get("id")), policy) for case in cases for policy in POLICIES}
    actual_pairs = {
        (str(row.get("case_id")), str(row.get("policy")))
        for row in exports
        if isinstance(row, dict)
    }
    if expected_pairs and actual_pairs != expected_pairs:
        failures.append("case/policy export matrix is incomplete or duplicated")

    export_paths: set[str] = set()
    for row in exports:
        if not isinstance(row, dict) or not row.get("ok"):
            failures.append("one or more export validation records are red")
            break
        if str(row.get("video_codec") or "") != OUTPUT_VIDEO_CODEC:
            failures.append("one or more exports are not H.264")
            break
        if str(row.get("audio_codec") or "") != OUTPUT_AUDIO_CODEC:
            failures.append("one or more exports are not AAC")
            break
        path_value = str(row.get("path") or "")
        if not path_value or path_value in export_paths:
            failures.append("export artifact paths are missing or duplicated")
            break
        export_paths.add(path_value)
        sha = str(row.get("sha256") or "")
        if len(sha) != 64:
            failures.append("one or more export SHA-256 values are missing")
            break

    for case in cases:
        if len(str(case.get("case_sha256") or "")) != 64:
            failures.append("one or more normalized case SHA-256 values are missing")
            break

    summary = report.get("summary") or {}
    if int(summary.get("scored_cases") or 0) < MIN_RELIABLY_SCORED_CASES:
        failures.append(
            f"fewer than {MIN_RELIABLY_SCORED_CASES} reliably face-scored cases"
        )
    if not bool(summary.get("evidence_valid")):
        failures.append("product framing evidence is not valid")
    if str(summary.get("verdict") or "") not in VALID_PRODUCT_VERDICTS:
        failures.append("product verdict is missing or not source-controlled")

    recorded_lock = report.get("threshold_lock") or {}
    if recorded_lock.get("threshold_sha256") != threshold_contract_sha256():
        failures.append("report threshold hash does not match source-controlled lock")

    return not failures, failures

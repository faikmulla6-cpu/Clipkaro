from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from app.services.asr_benchmark import (
    MIN_LANGUAGE_MATCH_RATE,
    MIN_TIMESTAMP_VALID_RATE,
    STRESS_SCENARIOS,
)
from app.services.asr_negative_controls import NEGATIVE_CONTROLS


QUALIFICATION_CONTRACT_VERSION = "2026-08-11-v1"
REQUIRED_LANGUAGE_FAMILIES = ("hi", "mr", "hinglish")
MIN_QUALIFICATION_CASES_PER_LANGUAGE = 2


def threshold_contract() -> dict[str, Any]:
    """Return the immutable quality contract that must be recorded with every verdict.

    The benchmark implementation remains the enforcement point. This normalized
    representation exists so the exact thresholds can be hashed before inference
    and checked again after inference; a result without an unchanged lock cannot
    become a production PASS.
    """
    return {
        "contract_version": QUALIFICATION_CONTRACT_VERSION,
        "required_language_families": list(REQUIRED_LANGUAGE_FAMILIES),
        "minimum_qualification_cases_per_language": MIN_QUALIFICATION_CASES_PER_LANGUAGE,
        "minimum_language_match_rate": MIN_LANGUAGE_MATCH_RATE,
        "minimum_timestamp_valid_rate": MIN_TIMESTAMP_VALID_RATE,
        "negative_controls": list(NEGATIVE_CONTROLS),
        "scenarios": [asdict(scenario) for scenario in STRESS_SCENARIOS],
    }


def threshold_contract_sha256() -> str:
    encoded = json.dumps(
        threshold_contract(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

"""Opt-in, deterministic Roman Hinglish caption presentation.

Raw ASR text and provider-native timings are intentionally left untouched.
Only ``display_text`` is changed, so all caption/export consumers can render
Roman text while debugging and provenance retain the original provider output.
"""
from __future__ import annotations

import re
from typing import Any

from .roman_hinglish_display_v1 import display_text, sha256 as display_sha256
from .roman_hinglish_policy_v3 import normalize_v3, policy_sha256

EXPECTED_V3 = "2bb7ed2f8e4c32782a030cfba19deb49875c32cdf29ba70ef7ce896f96cdfbe0"
EXPECTED_DISPLAY_V1 = "92992635e56181ebdb7ac748d9df73338ab465de0330c0eb7a821c59212a424e"
DEVANAGARI = re.compile(r"[\u0900-\u097f]")


def verify_frozen_policies() -> bool:
    return policy_sha256() == EXPECTED_V3 and display_sha256() == EXPECTED_DISPLAY_V1


def apply_roman_v3_display_v1(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply V3 then Display V1 once, without inventing or moving timing."""
    if not verify_frozen_policies():
        raise RuntimeError("Frozen Roman Hinglish V3 or Display V1 policy does not match its approved hash.")
    for segment in segments:
        if segment.get("roman_v3_applied") or segment.get("display_v1_applied"):
            raise RuntimeError("Roman Hinglish caption policies may be applied only once per transcript.")
        display_words: list[str] = []
        for word in segment.get("words") or []:
            raw = str(word.get("text") or "").strip()
            if not raw:
                continue
            roman = normalize_v3(raw)
            rendered = display_text(roman)
            word["roman_v3_text"] = roman
            word["display_text"] = rendered
            word["text_source"] = "roman_v3"
            word["timing_source"] = "ELEVENLABS_NATIVE_WORD"
            display_words.append(rendered)
        # Caption consumers use display_text, while the raw segment transcript
        # remains immutable.  Joining provider-native word spans avoids a second
        # segment-level normalization pass.
        segment["source_text"] = segment.get("text", "")
        segment["display_text"] = " ".join(display_words) or display_text(normalize_v3(str(segment.get("text") or "")))
        segment["roman_v3_applied"] = True
        segment["display_v1_applied"] = True
        segment["roman_hinglish_policy_v3_sha256"] = EXPECTED_V3
        segment["roman_hinglish_display_v1_sha256"] = EXPECTED_DISPLAY_V1
    return segments


def roman_caption_has_devanagari(segments: list[dict[str, Any]]) -> bool:
    return any(DEVANAGARI.search(str(word.get("display_text") or "")) for row in segments for word in row.get("words") or [])

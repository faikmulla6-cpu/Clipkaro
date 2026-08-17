"""Reference-blind deterministic Roman Hinglish Hybrid V3 generation."""
from __future__ import annotations

import difflib
import hashlib
import json
from typing import Any

from .roman_hinglish_policy_v3 import normalize_v3

HYBRID_VERSION = "2026-08-14-roman-hinglish-hybrid-v3"


def policy_payload() -> dict[str, object]:
    return {
        "version": HYBRID_VERSION,
        "base": "ElevenLabs canonical tokens remain authoritative",
        "secondaries": "Sarvam and Shunya must have exactly matching aligned operation",
        "alignment": "SequenceMatcher deterministic global opcode alignment, autojunk disabled",
        "substitution_limit": 3,
        "insertion_limit": 2,
        "deletion_limit": 2,
        "single_secondary_correction": "disallowed",
        "ambiguous_or_overlapping_operations": "keep base",
        "timestamps": "retain native base words where available; replacements inherit only base-span interval; insertions use derived_gap only",
        "forbidden": "no LLM, fuzzy matching, semantic rewrite, reference, score, provider ranking, or provider calls",
    }


def policy_sha256() -> str:
    return hashlib.sha256(json.dumps(policy_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _tokens(text: str) -> list[str]:
    return normalize_v3(text).split()


def _operations(base: list[str], secondary: list[str]) -> list[dict[str, Any]]:
    matcher = difflib.SequenceMatcher(a=base, b=secondary, autojunk=False)
    operations = []
    for tag, start, end, replacement_start, replacement_end in matcher.get_opcodes():
        if tag != "equal":
            operations.append({"tag": tag, "start": start, "end": end, "replacement": secondary[replacement_start:replacement_end]})
    return operations


def _allowed(operation: dict[str, Any]) -> bool:
    span, replacement = operation["end"] - operation["start"], len(operation["replacement"])
    if operation["tag"] == "replace": return 1 <= span <= 3 and 1 <= replacement <= 3
    if operation["tag"] == "insert": return span == 0 and 1 <= replacement <= 2
    if operation["tag"] == "delete": return 1 <= span <= 2 and replacement == 0
    return False


def _valid_interval(words: list[dict[str, Any]], start: int, end: int) -> tuple[float, float] | None:
    if start >= end or end > len(words): return None
    left, right = words[start], words[end - 1]
    try:
        begin, finish = float(left["start"]), float(right["end"])
    except (KeyError, TypeError, ValueError): return None
    return (begin, finish) if finish > begin else None


def generate(case_id: str, elevenlabs_text: str, sarvam_text: str | None, shunya_text: str, *, elevenlabs_words: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Generate a single output using only provider transcripts and timings."""
    base, sarvam, shunya = _tokens(elevenlabs_text), _tokens(sarvam_text or ""), _tokens(shunya_text)
    sarvam_ops = _operations(base, sarvam) if sarvam_text else []
    shunya_ops = _operations(base, shunya)
    shared = [operation for operation in sarvam_ops if operation in shunya_ops and _allowed(operation)]
    # Overlap or same-anchor ambiguity is fail-closed: retain the base span.
    accepted = []
    for operation in shared:
        if any(not (operation["end"] <= other["start"] or other["end"] <= operation["start"]) or (operation["start"] == other["start"] and operation["end"] == other["end"]) for other in accepted):
            continue
        accepted.append(operation)
    words = elevenlabs_words or []
    output: list[dict[str, Any]] = [{"token": token, "timestamp_source": "native_base_timestamp" if _valid_interval(words, index, index + 1) else "no_valid_timestamp"} for index, token in enumerate(base)]
    corrections = []
    for operation in sorted(accepted, key=lambda item: (item["start"], item["end"]), reverse=True):
        start, end, replacement = operation["start"], operation["end"], operation["replacement"]
        interval = _valid_interval(words, start, end)
        if operation["tag"] == "insert":
            source = "derived_gap" if _valid_interval(words, max(0, start - 1), min(len(words), start + 1)) else "no_valid_timestamp"
        else:
            source = "inherited_span_timestamp" if interval else "no_valid_timestamp"
        output[start:end] = [{"token": token, "timestamp_source": source, **({"start": interval[0], "end": interval[1]} if interval and operation["tag"] != "insert" else {})} for token in replacement]
        corrections.append({**operation, "timestamp_source": source})
    corrections.reverse()
    counts = {"substitutions": sum(item["tag"] == "replace" for item in corrections), "insertions": sum(item["tag"] == "insert" for item in corrections), "deletions": sum(item["tag"] == "delete" for item in corrections)}
    return {
        "case_id": case_id,
        "base_canonical": base,
        "sarvam_canonical": sarvam if sarvam_text else None,
        "shunya_canonical": shunya,
        "sarvam_available": bool(sarvam_text),
        "corrections": corrections,
        "counts": counts,
        "tokens": output,
        "hybrid_transcript": " ".join(item["token"] for item in output),
    }

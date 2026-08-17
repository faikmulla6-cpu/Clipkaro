"""Frozen, provider-independent Roman Hinglish scoring policy V3.

This module is for offline qualification only.  It does not alter stored
transcripts and it must never be used to pick different rules per provider or
per benchmark case.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from .asr_benchmark import _levenshtein
from .asr_policy_v2 import normalize_v2
from .roman_hindi import romanize_word

POLICY_VERSION = "2026-08-14-roman-hinglish-v3"
DEVANAGARI = re.compile(r"[\u0900-\u097f]")
LATIN = re.compile(r"[a-z]")

# These are globally defined orthographic canonicalisations, not benchmark
# cases.  The loanword entries are the mechanical IAST-derived forms emitted
# by the project transliterator for common English borrowings.
ORTHOGRAPHIC_CANONICAL_MAP = {
    "gayaa": "gaya",
    "gayee": "gayi",
    "kyonki": "kyunki",
    "kyuki": "kyunki",
    "kyaa": "kya",
    "naheen": "nahi",
    "nahee": "nahi",
    "klaaint": "client",
    "taaiming": "timing",
    "kainsal": "cancel",
}


def policy_payload() -> dict[str, object]:
    return {
        "version": POLICY_VERSION,
        "input_normalization": "V2 safe Unicode NFKC, annotations, punctuation, and spacing",
        "romanization": "Devanagari tokens use the deterministic project IAST transliterator then ASCII naturalization",
        "case": "casefold all Latin text",
        "orthographic_canonical_map": ORTHOGRAPHIC_CANONICAL_MAP,
        "loanword_rule": "only explicitly listed deterministic transliterator outputs are mapped to their Latin borrowing",
        "no_transliteration_matching": "no fuzzy matching, phonetic matching, provider-specific mapping, or per-case mapping",
        "scoring": "word and character Levenshtein after independent normalization of reference and hypothesis",
    }


def policy_sha256() -> str:
    return hashlib.sha256(
        json.dumps(policy_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def normalize_v3(text: str) -> str:
    """Produce a canonical Roman comparison representation, never a caption."""
    tokens: list[str] = []
    for token in normalize_v2(text).split():
        roman = romanize_word(token) if DEVANAGARI.search(token) else token
        canonical = ORTHOGRAPHIC_CANONICAL_MAP.get(roman.casefold(), roman.casefold())
        tokens.append(canonical)
    return " ".join(tokens)


def error_rate_v3(reference: str, hypothesis: str, *, unit: str = "word") -> float:
    reference_normalized, hypothesis_normalized = normalize_v3(reference), normalize_v3(hypothesis)
    left, right = (
        (reference_normalized.split(), hypothesis_normalized.split())
        if unit == "word"
        else (list(reference_normalized.replace(" ", "")), list(hypothesis_normalized.replace(" ", "")))
    )
    if not left:
        return 0.0 if not right else 1.0
    return _levenshtein(left, right) / len(left)


def edit_counts(reference: str, hypothesis: str) -> dict[str, int]:
    """Return deterministic Levenshtein edit counts for independently normalized text."""
    left, right = normalize_v3(reference).split(), normalize_v3(hypothesis).split()
    table = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for index in range(len(left) + 1): table[index][0] = index
    for index in range(len(right) + 1): table[0][index] = index
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            table[i][j] = min(table[i - 1][j] + 1, table[i][j - 1] + 1, table[i - 1][j - 1] + (left[i - 1] != right[j - 1]))
    i, j, counts = len(left), len(right), {"insertions": 0, "deletions": 0, "substitutions": 0}
    while i or j:
        if i and j and table[i][j] == table[i - 1][j - 1] + (left[i - 1] != right[j - 1]):
            if left[i - 1] != right[j - 1]: counts["substitutions"] += 1
            i, j = i - 1, j - 1
        elif i and table[i][j] == table[i - 1][j] + 1:
            counts["deletions"] += 1; i -= 1
        else:
            counts["insertions"] += 1; j -= 1
    return counts


def token_script_profile(tokens: Iterable[str]) -> dict[str, int]:
    values = list(tokens)
    return {
        "latin_tokens": sum(bool(LATIN.search(value.casefold())) for value in values),
        "devanagari_tokens": sum(bool(DEVANAGARI.search(value)) for value in values),
    }

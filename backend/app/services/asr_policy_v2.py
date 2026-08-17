"""Versioned offline qualification policy; never rewrites historical policy v1."""
from __future__ import annotations
import hashlib, json, re, unicodedata
from typing import Any
from .asr_benchmark import _levenshtein

POLICY_VERSION = "2026-08-13-v2"
_TOKEN_RE = re.compile(r"[\w\u0900-\u097f]+", re.UNICODE)
_NON_SPOKEN = re.compile(r"<[^>]*>|\{[^}]*\}|\[[^]]*\]")

def normalize_v2(text: str) -> str:
    """NFKC/casefold, strip declared dataset metadata and punctuation incl danda.

    The bracket rule only removes closed annotation constructs; ordinary unusual
    punctuation does not remove surrounding lexical words.  No transliteration
    or numeral rewriting is performed.
    """
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = _NON_SPOKEN.sub(" ", value).replace("\u200c", "").replace("\u200d", "")
    value = value.replace("\u0964", " ").replace("\u0965", " ")
    return " ".join(_TOKEN_RE.findall(value))

def error_rate_v2(reference: str, hypothesis: str, *, unit: str = "word") -> float:
    ref, hyp = normalize_v2(reference), normalize_v2(hypothesis)
    a,b=(ref.split(),hyp.split()) if unit == "word" else (list(ref.replace(" ","")),list(hyp.replace(" ","")))
    if not a: return 0.0 if not b else 1.0
    return _levenshtein(a,b)/len(a)

def policy_payload(thresholds: dict[str, Any]) -> dict[str, Any]:
    return {"version": POLICY_VERSION, "unicode":"NFKC then casefold", "zero_width":"remove ZWJ/ZWNJ", "punctuation":"remove standard punctuation plus U+0964/U+0965 danda", "annotations":"remove only complete <...>, {...}, [...] dataset metadata", "hinglish":"no transliteration, no numeral normalization, script differences remain lexical errors", "thresholds":thresholds}

def policy_sha256(thresholds: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(policy_payload(thresholds),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

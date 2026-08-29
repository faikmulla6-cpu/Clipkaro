import copy
import re
from collections import Counter
from typing import Any

from .asr_quality import segment_quality
from .roman_hindi import add_roman_display_text

DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
TOKEN_RE = re.compile(r"[\w\u0900-\u097f]+", re.UNICODE)
HINGLISH_TERMS = {
    "acha", "achha", "alag", "aur", "bas", "bhai", "college", "engineering",
    "exam", "ho", "hai", "haan", "karo", "ka", "ke", "ki", "kyu", "kyun",
    "matlab", "mujhe", "nahi", "placement", "scene", "samajh", "serious",
    "sir", "time", "toh", "yaar",
}
ENGLISH_MARKERS = {"actually", "basically", "college", "engineering", "placement", "serious", "time"}
ROMAN_CANONICAL = {
    "bhaaee": "bhai",
    "hai": "hai",
    "nahin": "nahi",
    "naheen": "nahi",
}


def _tokens(text: str) -> list[str]:
    return [item.casefold() for item in TOKEN_RE.findall(text)]


def _segment_confidence(segment: dict[str, Any]) -> float:
    words = segment.get("words") or []
    scored = [float(word.get("confidence", 1)) for word in words if word.get("confidence") is not None]
    if scored:
        return sum(scored) / len(scored)
    if segment.get("avg_logprob") is not None:
        return max(0.0, min(1.0, (float(segment.get("avg_logprob", -1.2)) + 1.8) / 1.8))
    return 1.0


def _is_low_confidence(segment: dict[str, Any]) -> bool:
    words = segment.get("words") or []
    if len(words) >= 3 and _segment_confidence(segment) < .55:
        return True
    return bool(segment.get("review_required"))


def _naturalize_common_roman_words(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for segment in segments:
        if segment.get("display_text"):
            tokens = str(segment["display_text"]).split()
            segment["display_text"] = " ".join(ROMAN_CANONICAL.get(token.casefold(), token) for token in tokens)
        for word in segment.get("words") or []:
            value = str(word.get("display_text") or "").strip()
            if value:
                word["display_text"] = ROMAN_CANONICAL.get(value.casefold(), value)
    return segments


def language_profile(segments: list[dict[str, Any]], language: str = "") -> dict[str, Any]:
    text = " ".join(str(item.get("display_text") or item.get("text") or "") for item in segments)
    tokens = _tokens(text)
    latin_terms = [token for token in tokens if not DEVANAGARI_RE.search(token)]
    hinglish_hits = sum(1 for token in latin_terms if token in HINGLISH_TERMS)
    english_hits = sum(1 for token in latin_terms if token in ENGLISH_MARKERS)
    devanagari_hits = len(DEVANAGARI_RE.findall(text))
    code_switch_score = 0.0
    if tokens:
        code_switch_score = min(1.0, (hinglish_hits + min(english_hits, hinglish_hits)) / max(5, len(tokens) * .3))
    likely = "english"
    if devanagari_hits and latin_terms:
        likely = "hinglish"
    elif language in {"hi", "ur"}:
        likely = "hindi"
    elif language == "hinglish" or code_switch_score >= .55:
        likely = "hinglish"
    return {
        "likely_language_style": likely,
        "india_quality_suitable": likely in {"hindi", "hinglish"} or hinglish_hits >= 2,
        "code_switch_score": round(code_switch_score, 3),
        "hinglish_term_hits": hinglish_hits,
        "devanagari_character_count": devanagari_hits,
    }


def review_signal(segment: dict[str, Any], language: str = "") -> dict[str, Any]:
    quality = segment_quality(segment, language)
    reasons = list(quality.get("flags") or [])
    confidence = _segment_confidence(segment)
    words = segment.get("words") or []
    if len(words) >= 3 and confidence < .55:
        reasons.append("low_word_confidence")
    short_uncertain = (
        max(0.0, float(segment.get("end", 0)) - float(segment.get("start", 0))) < 1.2
        and len(_tokens(str(segment.get("text") or ""))) <= 3
        and confidence < .68
    )
    if short_uncertain:
        reasons.append("short_uncertain_segment")
    counts = Counter(_tokens(str(segment.get("text") or "")))
    if any(count >= 4 for count in counts.values()):
        reasons.append("repeated_token_review")
    deduped = list(dict.fromkeys(reasons))
    return {
        "review_suggested": bool(deduped),
        "review_reasons": deduped,
        "word_confidence": round(confidence, 3),
    }


def transcript_review_summary(segments: list[dict[str, Any]], language: str = "") -> dict[str, Any]:
    flagged = [review_signal(segment, language) for segment in segments]
    reasons = list(dict.fromkeys(reason for item in flagged for reason in item["review_reasons"]))
    return {
        "review_suggested": bool(reasons),
        "review_reasons": reasons[:5],
        "review_segment_count": sum(1 for item in flagged if item["review_suggested"]),
    }


def caption_segments_for_export(
    segments: list[dict[str, Any]],
    language: str = "",
    *,
    india_quality_mode: bool = False,
    caption_language_style: str = "auto",
) -> list[dict[str, Any]]:
    if not india_quality_mode or caption_language_style == "original":
        return copy.deepcopy(segments)
    prepared = copy.deepcopy(segments)
    profile = language_profile(prepared, language)
    wants_roman = caption_language_style == "roman_hinglish" or (
        caption_language_style == "auto" and profile["likely_language_style"] == "hinglish"
    )
    if not wants_roman or not profile["india_quality_suitable"]:
        return prepared
    reliable = [segment for segment in prepared if not _is_low_confidence(segment)]
    if not reliable:
        return prepared
    converted = _naturalize_common_roman_words(add_roman_display_text(reliable, True))
    by_identity = {id(original): converted[index] for index, original in enumerate(reliable)}
    return [by_identity.get(id(segment), segment) for segment in prepared]


def effective_caption_position(india_quality_mode: bool, preserve_source_captions: bool,
                               caption_position: str) -> str:
    if india_quality_mode and preserve_source_captions and caption_position == "bottom":
        return "above"
    return caption_position

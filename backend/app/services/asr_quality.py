import re
from collections import Counter
from typing import Any

TOKEN_RE = re.compile(r"[\w\u0900-\u097f]+", re.UNICODE)
FOREIGN_RE = re.compile(r"[\u0600-\u06ff\u0980-\u0dff\u1100-\u11ff\u3040-\u30ff\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(text)]


def segment_quality(segment: dict[str, Any], language: str = "") -> dict[str, Any]:
    text = str(segment.get("text", ""))
    tokens = _tokens(text)
    counts = Counter(tokens)
    dominant = max(counts.values(), default=0) / max(len(tokens), 1)
    diversity = len(counts) / max(len(tokens), 1)
    longest = 1
    run = 1
    for a, b in zip(tokens, tokens[1:]):
        run = run + 1 if a == b else 1
        longest = max(longest, run)
    words = segment.get("words") or []
    collapsed = sum(float(w.get("end", 0)) <= float(w.get("start", 0)) for w in words) / max(len(words), 1)
    confidence = sum(float(w.get("confidence", 0)) for w in words) / max(len(words), 1) if words else 0
    duration = max(float(segment.get("end", 0)) - float(segment.get("start", 0)), .01)
    foreign = len(FOREIGN_RE.findall(text)) / max(sum(ch.isalpha() for ch in text), 1)
    flags = []
    if len(tokens) >= 8 and dominant >= .55: flags.append("dominant_repetition")
    if longest >= 5: flags.append("consecutive_repetition")
    if words and collapsed >= .2: flags.append("collapsed_word_timestamps")
    if len(tokens) / duration > 5.5: flags.append("implausible_speech_rate")
    if float(segment.get("no_speech_prob", 0)) > .65: flags.append("probable_non_speech")
    if float(segment.get("compression_ratio", 0)) > 2.4: flags.append("compression_repetition")
    if language in {"hi", "hinglish"} and foreign > .02: flags.append("foreign_script")
    return {"accepted": not flags, "flags": flags, "token_diversity": round(diversity, 3),
            "dominant_token_ratio": round(dominant, 3), "collapsed_timestamp_ratio": round(collapsed, 3),
            "word_confidence": round(confidence, 3), "foreign_script_ratio": round(foreign, 3)}


def assess_transcript(segments: list[dict[str, Any]], language: str = "", *, min_clean_seconds: float = 20.0) -> dict[str, Any]:
    results = [segment_quality(s, language) for s in segments]
    accepted = [s for s, q in zip(segments, results) if q["accepted"]]
    clean_duration = sum(max(0, float(s["end"]) - float(s["start"])) for s in accepted)
    total_duration = sum(max(0, float(s["end"]) - float(s["start"])) for s in segments)
    flags = sorted({f for q in results for f in q["flags"]})
    return {"accepted": bool(accepted) and clean_duration >= min_clean_seconds and clean_duration / max(total_duration, .01) >= .4,
            "segments": accepted, "flags": flags, "clean_duration": clean_duration,
            "speech_coverage": clean_duration / max(total_duration, .01)}

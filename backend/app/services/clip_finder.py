import re
import uuid
from typing import Any
from .asr_quality import segment_quality

# Signals are deliberately multilingual and evidence-based. They do not invent
# virality; they only score language that actually exists in the transcript.
HOOKS = {
    "question": (r"\b(why|how|what if|did you know|have you ever|kyun|kyu|kaise|kya|kab|pata hai)\b|[?？]", 13, "Opens a curiosity gap"),
    "warning": (r"\b(mistake|avoid|never|warning|stop|wrong|galti|bacho|kabhi mat|mat karo|dhyan)\b|गलती|मत करो|सावधान", 15, "Strong mistake or warning hook"),
    "surprise": (r"\b(surprising|secret|nobody|truth|actually|unexpected|sach|raaz|asli|hairan|kisi ko nahi)\b|सच|राज़|असली|हैरान", 14, "Contains a surprising insight"),
    "steps": (r"\b(step|first|second|third|tips?|ways?|system|formula|tarika|tareeka|pehle|dusra|teen)\b|तरीका|पहले|दूसरा|तीन", 12, "Clear actionable structure"),
    "growth": (r"\b(grow|money|business|sales|profit|audience|customers?|paise|paisa|kamai|dhandha|business)\b|पैसे|कमाई|बिज़नेस", 10, "Relevant business or growth insight"),
    "emotion": (r"\b(felt|fear|failed|struggle|love|proud|changed my life|darr|haar|fail|mushkil|pyaar|zindagi badal)\b|डर|मुश्किल|प्यार|ज़िंदगी बदल", 10, "Emotionally resonant moment"),
    "opinion": (r"\b(i disagree|unpopular opinion|most people are wrong|main nahi maanta|meri baat mano|sab galat)\b|मैं नहीं मानता|सब गलत", 12, "Strong opinion or tension"),
    "revelation": (r"\b(realized|discovered|found out|tab samajh|mujhe pata chala|asal mein)\b|तब समझ|पता चला|असल में", 12, "Clear revelation or payoff"),
}

OPENING_FILLER = re.compile(
    r"^(so|and|but|well|okay|ok|um+|uh+|toh?|aur|lekin|matlab|haan|acha|achha|bas)\b[, ]*",
    re.I,
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+", text.strip()) if s.strip()]


def _title(text: str) -> str:
    sentence = _sentences(text)[0] if _sentences(text) else text
    sentence = OPENING_FILLER.sub("", sentence)
    return " ".join(sentence.split()[:10]).rstrip(".,!?।").capitalize()


def content_profile(segments: list[dict[str, Any]]) -> dict[str, str | float]:
    text = " ".join(str(s.get("display_text") or s.get("text", "")) for s in segments).casefold()
    duration = max(float(segments[-1]["end"]) - float(segments[0]["start"]), 1.0)
    words_per_minute = len(text.split()) * 60 / duration
    if re.search(r"\b(step|how to|tutorial|formula|tarika|tareeka|kaise kare|पहले|तरीका)\b", text):
        content_type = "tutorial"
    elif text.count("?") >= max(2, len(segments) // 5):
        content_type = "interview"
    elif re.search(r"\b(then i|when i|my story|mere saath|phir maine|ek baar|मेरे साथ|फिर मैंने)\b", text):
        content_type = "story"
    elif re.search(r"\b(i think|in my opinion|main maanta|mere hisab|मुझे लगता|मेरे हिसाब)\b", text):
        content_type = "commentary"
    else:
        content_type = "general"
    density = "high" if words_per_minute >= 145 else "low" if words_per_minute < 90 else "medium"
    return {"content_type": content_type, "density": density,
            "words_per_minute": round(words_per_minute, 1)}


def _duration_score(duration: float, content_type: str, density: str) -> float:
    ideal = (28, 60) if density == "high" else (40, 78)
    if content_type == "story": ideal = (45, 90)
    if ideal[0] <= duration <= ideal[1]: return 9
    if 20 <= duration <= 90: return 4
    return 0


def _score(text: str, opening: str, duration: float,
           profile: dict[str, str | float]) -> tuple[float, list[str], dict[str, float]]:
    lower, opening_lower = text.casefold(), opening.casefold()
    score, reasons = 38.0, []
    breakdown = {"hook": 38.0, "clarity": 58.0, "value": 50.0,
                 "emotion": 38.0, "flow": 55.0}
    for key, (pattern, points, reason) in HOOKS.items():
        if not re.search(pattern, lower, re.I): continue
        reasons.append(reason)
        opening_match = bool(re.search(pattern, opening_lower, re.I))
        earned = points if opening_match else points * .45
        score += earned
        if key in {"question", "warning", "surprise", "opinion"}:
            breakdown["hook"] += points * (2.4 if opening_match else .7)
        if key in {"steps", "growth", "revelation"}: breakdown["value"] += points * 2
        if key == "emotion": breakdown["emotion"] += points * 3
    word_count = len(text.split())
    if 45 <= word_count <= 190: score += 8; breakdown["clarity"] += 18
    if text.rstrip().endswith((".", "!", "?", "।")): score += 6; breakdown["flow"] += 17
    else: score -= 7; breakdown["flow"] -= 12
    if len(_sentences(text)) >= 2: score += 4; breakdown["flow"] += 8
    score += _duration_score(duration, str(profile["content_type"]), str(profile["density"]))
    if OPENING_FILLER.match(opening):
        score -= 5; breakdown["hook"] -= 10
    if len(opening.split()) < 4:
        score -= 4; breakdown["clarity"] -= 8
    breakdown = {key: max(0.0, min(round(value, 1), 98.0)) for key, value in breakdown.items()}
    return max(0.0, min(round(score, 1), 98.0)), list(dict.fromkeys(reasons)), breakdown


def overlap_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    overlap = max(0.0, min(float(left["end_time"]), float(right["end_time"])) -
                  max(float(left["start_time"]), float(right["start_time"])))
    shorter = min(float(left["end_time"]) - float(left["start_time"]),
                  float(right["end_time"]) - float(right["start_time"]))
    return overlap / max(shorter, .001)


def _word_text(word: dict[str, Any]) -> str:
    """Return the display form without changing the provider-native word."""
    return str(word.get("display_text") or word.get("roman_v3_text") or word.get("text") or "").strip()


def _word_aligned_windows(segment: dict[str, Any], target_seconds: float = 55.0) -> list[dict[str, Any]]:
    """Split a long provider segment using only its genuine word boundaries.

    Some hosted ASR APIs return multi-minute chunks even when every word carries
    an accurate timestamp.  Clip ranking deliberately accepts only complete
    20–90 second moments, so those API chunks need presentation-level windows.
    The stored transcript is never changed and no word timing is invented here.
    """
    start, end = float(segment.get("start", 0)), float(segment.get("end", 0))
    if end - start <= 90:
        return [segment]
    words = []
    for word in segment.get("words") or []:
        try:
            word_start, word_end = float(word.get("start")), float(word.get("end"))
        except (TypeError, ValueError):
            continue
        if word_end <= word_start or word_start < start or word_end > end:
            continue
        if _word_text(word):
            words.append((word_start, word_end, word))
    if not words:
        # Without native word timing it is unsafe to manufacture a boundary.
        return [segment]
    words.sort(key=lambda item: (item[0], item[1]))

    groups: list[list[tuple[float, float, dict[str, Any]]]] = []
    current: list[tuple[float, float, dict[str, Any]]] = []
    for word in words:
        if current and word[1] - current[0][0] > target_seconds:
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    # A short final tail is not a complete clip.  Merge it back when doing so
    # remains within the selector's 90-second upper bound.
    if len(groups) > 1 and groups[-1][-1][1] - groups[-1][0][0] < 20:
        merged_duration = groups[-1][-1][1] - groups[-2][0][0]
        if merged_duration <= 90:
            groups[-2].extend(groups.pop())

    windows: list[dict[str, Any]] = []
    for group in groups:
        window_start, window_end = group[0][0], group[-1][1]
        # Tiny gaps/partial tails cannot be a valid source moment.  They are
        # retained in the saved transcript but excluded from ranking only.
        if window_end - window_start < 20:
            continue
        window_words = [dict(word) for _, _, word in group]
        window = dict(segment)
        window.update({
            "start": window_start,
            "end": window_end,
            "words": window_words,
            "text": " ".join(_word_text(word) for word in window_words),
        })
        if segment.get("display_text") is not None:
            window["display_text"] = " ".join(_word_text(word) for word in window_words)
        windows.append(window)
    return windows or [segment]


def _clip_ready_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand only long, word-timestamped API chunks for candidate selection."""
    expanded: list[dict[str, Any]] = []
    for segment in segments:
        expanded.extend(_word_aligned_windows(segment))
    return expanded


def _ranked_candidates(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments = [segment for segment in _clip_ready_segments(segments) if segment_quality(segment).get("accepted")]
    if not segments: return []
    profile = content_profile(segments)
    candidates: list[dict[str, Any]] = []
    for start_idx in range(len(segments)):
        text_parts: list[str] = []
        for end_idx in range(start_idx, len(segments)):
            duration = float(segments[end_idx]["end"]) - float(segments[start_idx]["start"])
            if duration > 90: break
            text_parts.append(str(segments[end_idx].get("display_text") or segments[end_idx]["text"]).strip())
            if duration < 20: continue
            text = " ".join(text_parts)
            opening = text_parts[0]
            score, reasons, breakdown = _score(text, opening, duration, profile)
            candidates.append({
                "id": str(uuid.uuid4()), "start_time": float(segments[start_idx]["start"]),
                "end_time": float(segments[end_idx]["end"]), "hook": (_sentences(opening) or [opening])[0][:100],
                "title": _title(opening), "reason": ". ".join(reasons[:2]) or "Complete, high-confidence moment",
                "score": score, "platform": "YouTube Shorts" if duration <= 60 else "Instagram Reels",
                "score_breakdown": breakdown,
                "status": "suggested", "text": text,
            })
    return sorted(candidates, key=lambda item: (item["score"], item["score_breakdown"]["hook"]), reverse=True)


def _select_non_overlapping(ranked: list[dict[str, Any]], limit: int, max_overlap: float) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for clip in ranked:
        if all(overlap_ratio(clip, existing) <= max_overlap for existing in selected):
            selected.append(clip)
        if len(selected) >= limit: break
    return selected


def candidate_clips(segments: list[dict[str, Any]], limit: int = 16) -> list[dict[str, Any]]:
    """Return a diverse, high-recall pool for a semantic reranker.

    A looser overlap threshold preserves useful alternative boundaries around a
    strong moment while preventing one topic from consuming the whole LLM prompt.
    """
    return _select_non_overlapping(_ranked_candidates(segments), max(1, limit), .78)


def find_clips(segments: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Rank complete 20–90s moments with multilingual, content-aware evidence."""
    return _select_non_overlapping(_ranked_candidates(segments), limit, .5)

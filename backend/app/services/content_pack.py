import json
import re
import uuid
from typing import Any

from app.core.database import execute, fetch_one
from app.services.clip_finder import content_profile
from app.services.india_quality import SUSPICIOUS_ROMAN_TOKENS, language_profile, review_signal
from app.services.jobs import utcnow

FORBIDDEN_CLICHES = (
    "in today's fast-paced world", "unlock the power of", "game changer",
    "dive deep", "viral", "guaranteed",
)
STOPWORDS = {
    "about", "after", "again", "because", "before", "being", "could", "every",
    "from", "have", "into", "that", "their", "there", "these", "this", "when",
    "where", "with", "your", "hai", "hain", "hota", "hoti", "ka", "ke", "ki",
    "ko", "me", "mein", "aur", "the", "and", "for", "you", "are", "has",
    "pata", "kaun", "sab", "sabko", "bas", "itna", "mujhe", "chala", "nahi",
    "nobody", "talks", "knows", "full", "plan", "truth", "funniest", "year",
    "time", "scene", "saath", "hua", "like", "first", "real", "lesson",
    "bolte", "karte", "thinking", "expecting", "coming",
}
SOURCE_PHRASES = (
    "crowd work", "group project", "network issue", "college life",
    "placement", "attendance", "engineering", "jugaad", "semester",
    "practical", "deadline", "submission", "viva", "coding",
)
REVIEW_NEEDED_COPY = "This clip has a flagged transcript line. Review it before publishing polished copy."


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for phrase in FORBIDDEN_CLICHES:
        text = re.sub(re.escape(phrase), "", text, flags=re.I)
    text = text.strip(" -")
    if len(text) <= limit:
        return text
    return (text[:limit + 1].rsplit(" ", 1)[0] or text[:limit]).strip(" -")


def _tokens(text: str) -> list[str]:
    return [item.casefold() for item in re.findall(r"[\w\u0900-\u097f]+", text, re.UNICODE)]


def _keywords(text: str, limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    original: dict[str, str] = {}
    lower = text.casefold()
    for phrase in SOURCE_PHRASES:
        if phrase in lower:
            key = phrase.replace(" ", "_")
            counts[key] = lower.count(phrase)
            original[key] = phrase
    for token in re.findall(r"[\w\u0900-\u097f]+", text, re.UNICODE):
        key = token.casefold()
        if len(key) < 3 or key in STOPWORDS or key in SUSPICIOUS_ROMAN_TOKENS:
            continue
        counts[key] = counts.get(key, 0) + 1
        original.setdefault(key, token)
    ranked = sorted(counts, key=lambda key: (counts[key], len(key)), reverse=True)
    return [original[key] for key in ranked[:limit]]


def _safe_segment_text(segment: dict[str, Any], language: str) -> str:
    text = str(segment.get("display_text") or segment.get("text") or "").strip()
    if not text:
        return ""
    if segment.get("corrected_text"):
        return text
    signal = review_signal(segment, language)
    risky_reasons = {
        "low_word_confidence",
        "repeated_token_review",
        "phonetic_spelling_review",
        "review_required",
    }
    if signal["review_suggested"] and any(reason in risky_reasons for reason in signal["review_reasons"]):
        return ""
    return text


def _clip_source_text(
    clip: dict[str, Any],
    segments: list[dict[str, Any]],
    language: str,
) -> tuple[str, bool]:
    overlapping = [
        segment for segment in segments
        if float(segment.get("end", 0)) > float(clip.get("start_time", 0))
        and float(segment.get("start", 0)) < float(clip.get("end_time", 0))
    ]
    safe_parts = [_safe_segment_text(segment, language) for segment in overlapping]
    safe_text = _clean_text(" ".join(part for part in safe_parts if part), 1800)
    needs_review = any(not part and str(segment.get("text") or "").strip() for part, segment in zip(safe_parts, overlapping))
    if safe_text:
        return safe_text, needs_review
    if needs_review:
        return "Flagged transcript moment", True
    fallback = _clean_text(clip.get("title") or clip.get("reason") or clip.get("hook") or "This clip", 1800)
    return fallback, needs_review


def _hashtag(value: str) -> str:
    cleaned = re.sub(r"[^\w\u0900-\u097f]", "", value, flags=re.UNICODE)
    return f"#{cleaned[:32]}" if cleaned else ""


def _hashtags(text: str, language: str, category: str, limit: int = 7) -> list[str]:
    base = ["ClipKaro", category.title() if category and category != "auto" else ""]
    if language in {"hi", "hinglish"}:
        base.extend(["Hinglish", "IndianCreators"])
    base.extend(_keywords(text, 8))
    tags = []
    for item in base:
        tag = _hashtag(item)
        if tag and tag.casefold() not in {x.casefold() for x in tags}:
            tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def _sentence(text: str, fallback: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?।])\s+", text) if part.strip()]
    return _clean_text(parts[0] if parts else fallback, 150)


def _short_title(text: str, fallback: str, words: int = 9) -> str:
    cleaned = _clean_text(text, 260).strip("“”\"'")
    return " ".join(cleaned.split()[:words]).rstrip(".,!?।") or fallback


def _title_options(clip: dict[str, Any], keywords: list[str], language: str) -> list[str]:
    hook = _short_title(clip.get("hook") or clip.get("title"), "Best moment")
    topic = keywords[0].title() if keywords else _short_title(clip.get("title"), "This moment", 4)
    if language in {"hi", "hinglish"}:
        direct = hook if any(word in hook.casefold() for word in ("bhai", "ka", "ke", "hai")) else f"{hook} ka scene"
        topic_title = f"That {topic} moment hits too close"
    else:
        direct = hook
        topic_title = f"The {topic} moment that explains it"
    options = list(dict.fromkeys([
        _clean_text(direct, 70),
        _clean_text(topic_title, 70),
        _clean_text(str(clip.get("title") or hook), 70),
        _clean_text(f"{topic} ka real scene" if language in {"hi", "hinglish"} else f"The real {topic} moment", 70),
    ]))
    while len(options) < 3:
        options.append(f"ClipKaro moment {len(options) + 1}")
    return options[:3]


def _linkedin_relevance(category: str, text: str) -> bool:
    if category in {"business", "education", "podcast", "motivation"}:
        return True
    lower = text.casefold()
    return any(term in lower for term in ("career", "business", "lesson", "work", "startup", "coding", "project"))


def _clip_pack(clip: dict[str, Any], segments: list[dict[str, Any]], language: str, category: str) -> dict[str, Any]:
    text, needs_review = _clip_source_text(clip, segments, language)
    display_title = "Flagged transcript moment" if needs_review else (clip.get("title") or "")
    option_source = {**clip, "title": display_title, "hook": text}
    keywords = _keywords(text)
    tags = _hashtags(text, language, category)
    hook = REVIEW_NEEDED_COPY if needs_review and not keywords else _sentence(text or clip.get("hook"), str(clip.get("title") or "This clip"))
    titles = _title_options(option_source, keywords, language)
    context = _short_title(text, hook, 16)
    tone_question = "Ye scene aapke saath bhi hua hai?" if language in {"hi", "hinglish"} else "Have you seen this happen too?"
    youtube_description = _clean_text(
        f"{hook}\n\nWatch this short for the setup, the specific detail, and the payoff around {', '.join(keywords[:3]) or context}.",
        420,
    )
    instagram_caption = _clean_text(f"{hook}\n\n{tone_question}", 240)
    x_post = _clean_text(f"{hook} {tone_question}", 220)
    linkedin = (
        _clean_text(f"{hook}\n\nA sharp reminder from this clip: {context}.", 500)
        if _linkedin_relevance(category, text)
        else "Not recommended for this clip"
    )
    thumb_base = [word.upper() for word in keywords[:4]]
    thumbnail = list(dict.fromkeys([
        _clean_text(" ".join(thumb_base[:3]) or _short_title(hook, "BEST MOMENT", 4).upper(), 34),
        _clean_text(_short_title(hook, "WATCH THIS", 4).upper(), 34),
        _clean_text(display_title.upper().split("?")[0] or "THIS MOMENT", 34),
        _clean_text("WATCH THIS MOMENT", 34),
        _clean_text("REAL CLIP PAYOFF", 34),
    ]))
    while len(thumbnail) < 3:
        thumbnail.append(f"CLIP MOMENT {len(thumbnail) + 1}")
    thumbnail = thumbnail[:3]
    return {
        "clip_id": clip["id"],
        "clip_title": display_title,
        "needs_transcript_review": needs_review,
        "youtube_shorts": {"titles": titles, "description": youtube_description, "hashtags": tags[:6]},
        "instagram_reels": {"caption": instagram_caption, "hashtags": tags[:7]},
        "x": {"post": x_post},
        "linkedin": {"post": linkedin, "recommended": linkedin != "Not recommended for this clip"},
        "thumbnail_text": thumbnail,
    }


def _content_angles(segments: list[dict[str, Any]], clips: list[dict[str, Any]], language: str) -> list[str]:
    text = " ".join(
        _safe_segment_text(segment, language)
        for segment in segments
    )
    lower = text.casefold()
    angles = []
    if "engineering" in lower:
        angles.append("Engineering-life truths")
    if "placement" in lower or "attendance" in lower:
        angles.append("Placement and attendance panic")
    if "group project" in lower or "deadline" in lower or "submission" in lower:
        angles.append("Group-project deadline chaos")
    if "crowd work" in lower:
        angles.append("How crowd work finds a payoff")
    keywords = [item for item in _keywords(text, 10) if item.title() not in {angle.split()[0] for angle in angles}]
    angles.extend(f"{item.title()} moments from the source" for item in keywords[:3])
    if any("?" in str(clip.get("hook") or "") for clip in clips):
        angles.append("Question-led hooks from audience reactions")
    if any("lesson" in str(clip.get("transcript_text") or "").casefold() for clip in clips):
        angles.append("Lessons creators can turn into explainers")
    return list(dict.fromkeys(angles))[:5] or ["Strongest standalone moments from the video"]


def _summary(project: dict[str, Any], source_text: str) -> str:
    title = str(project.get("title") or "This video")
    keywords = _keywords(source_text, 6)
    lower = source_text.casefold()
    if "engineering" in lower and ("placement" in lower or "group project" in lower):
        return _clean_text(
            f"{title} turns engineering life into comedy through placement pressure, attendance panic, jugaad, viva explanations, deadlines, and group-project excuses.",
            260,
        )
    return _clean_text(f"{title} covers {', '.join(keywords) or 'the strongest source moments'}.", 260)


def generate_content_pack(project: dict[str, Any], clips: list[dict[str, Any]],
                          segments: list[dict[str, Any]], language: str) -> dict[str, Any]:
    category = str(project.get("category") or "auto")
    source_text = " ".join(_safe_segment_text(segment, language) for segment in segments)
    profile = content_profile(segments) if segments else {"content_type": category, "density": "medium"}
    lang_profile = language_profile(segments, language)
    ordered = sorted(clips, key=lambda clip: (float(clip.get("score") or 0), float((clip.get("score_breakdown") or {}).get("hook", 0))), reverse=True)
    payload = {
        "version": "content-pack-mvp-1",
        "project_id": project["id"],
        "generated_at": utcnow(),
        "language": language,
        "language_style": lang_profile["likely_language_style"],
        "content_summary": _summary(project, source_text),
        "content_angles": _content_angles(segments, ordered, language),
        "best_clips_order": [
            {
                "clip_id": clip["id"],
                "rank": index + 1,
                "reason": _clean_text(clip.get("reason") or f"{profile['content_type']} moment with score {clip.get('score')}", 180),
            }
            for index, clip in enumerate(ordered)
        ],
        "clips": [_clip_pack(clip, segments, language, category) for clip in ordered],
    }
    validate_content_pack(payload)
    return payload


def validate_content_pack(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("clips"), list):
        raise ValueError("Content Pack response is missing clips.")
    for clip in payload["clips"]:
        titles = ((clip.get("youtube_shorts") or {}).get("titles") or [])
        if len(titles) != 3 or any(not _clean_text(title, 90) for title in titles):
            raise ValueError("Content Pack response has malformed YouTube titles.")
        if not (clip.get("instagram_reels") or {}).get("caption"):
            raise ValueError("Content Pack response is missing Instagram caption.")
        if not (clip.get("x") or {}).get("post"):
            raise ValueError("Content Pack response is missing X post.")
        if len(clip.get("thumbnail_text") or []) != 3:
            raise ValueError("Content Pack response is missing thumbnail text.")


async def persist_content_pack(project_id: str, payload: dict[str, Any],
                               *, status: str = "ready", provider: str = "deterministic") -> dict[str, Any]:
    timestamp = utcnow()
    existing = await fetch_one("SELECT id FROM content_packs WHERE project_id=?", (project_id,))
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if existing:
        await execute(
            "UPDATE content_packs SET status=?,payload_json=?,provider=?,updated_at=? WHERE project_id=?",
            (status, body, provider, timestamp, project_id),
        )
    else:
        await execute(
            "INSERT INTO content_packs(id,project_id,status,payload_json,provider,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), project_id, status, body, provider, timestamp, timestamp),
        )
    row = await fetch_one("SELECT * FROM content_packs WHERE project_id=?", (project_id,))
    return _row_to_response(row)


def _row_to_response(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"status": "missing", "content_pack": None}
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    return {
        "status": row.get("status") or "failed",
        "content_pack": payload,
        "provider": row.get("provider") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }

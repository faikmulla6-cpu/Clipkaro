from __future__ import annotations

import html
import re
from typing import Any, Iterable

TICKS_PER_SECOND = 10_000_000


def normalize_word_boundaries(
    boundaries: Iterable[dict[str, Any]],
    *,
    audio_duration: float,
    global_start: float = 0.0,
    speaker_id: str = "",
    track: str = "dialogue",
    fallback_word_seconds: float = 0.24,
) -> list[dict[str, Any]]:
    """Convert Edge TTS WordBoundary events (100 ns ticks) to safe global seconds."""
    rows = []
    for item in boundaries:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        try:
            raw_offset = float(item.get("offset", 0))
            if raw_offset < 0:
                continue
            offset = raw_offset / TICKS_PER_SECOND
            duration = max(0.0, float(item.get("duration", 0)) / TICKS_PER_SECOND)
        except (TypeError, ValueError):
            continue
        if text:
            rows.append({"text": text, "local_start": offset, "local_duration": duration})

    rows.sort(key=lambda item: item["local_start"])
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        start = min(max(0.0, item["local_start"]), max(0.0, audio_duration))
        end = start + item["local_duration"]
        if item["local_duration"] <= 0:
            if index + 1 < len(rows):
                next_start = rows[index + 1]["local_start"]
                end = next_start if next_start > start else start + fallback_word_seconds
            else:
                end = start + fallback_word_seconds
        end = min(max(start, end), max(0.0, audio_duration))
        if end <= start:
            end = min(max(0.0, audio_duration), start + fallback_word_seconds)
        if end <= start:
            continue
        normalized.append({
            "text": item["text"],
            "start_seconds": round(global_start + start, 4),
            "end_seconds": round(global_start + end, 4),
            "speaker_id": speaker_id,
            "track": track,
            "source": "tts_word_boundary",
        })
    return normalized


def approximate_word_boundaries(
    text: str,
    *,
    audio_duration: float,
    global_start: float = 0.0,
    speaker_id: str = "",
    track: str = "dialogue",
) -> list[dict[str, Any]]:
    """Explicitly approximate phrase timing when a TTS provider returns no alignment."""
    words = re.findall(r"\S+", str(text or "").strip())
    if not words or audio_duration <= 0:
        return []
    weights = [max(1, len(word.strip("ØŒÛ”!?.,:;ØŸ")) ** 0.72) for word in words]
    total = float(sum(weights))
    cursor = 0.0
    output = []
    for word, weight in zip(words, weights):
        start = audio_duration * cursor / total
        cursor += weight
        end = audio_duration * cursor / total
        output.append({
            "text": word,
            "start_seconds": round(global_start + start, 4),
            "end_seconds": round(global_start + end, 4),
            "speaker_id": speaker_id,
            "track": track,
            "source": "estimated_from_text",
        })
    return output


def group_caption_phrases(
    words: list[dict[str, Any]],
    *,
    max_words: int = 8,
    max_chars: int = 52,
    max_duration: float = 4.0,
) -> list[list[dict[str, Any]]]:
    """Group timed words into readable lines, merging short phrases for a legible hold."""
    phrases: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for word in words:
        token = str(word.get("text") or "")
        token_start = float(word.get("start_seconds") or 0)
        token_end = float(word.get("end_seconds") or token_start)
        current_start = float(current[0].get("start_seconds") or token_start) if current else token_start
        current_end = max((float(item.get("end_seconds") or token_start) for item in current), default=token_start)
        gap_seconds = max(0.0, token_start - current_end)
        should_break = bool(current) and (
            len(current) >= max_words
            or current_chars + len(token) + 1 > max_chars
            or token_end - current_start > max_duration
            or gap_seconds > 0.65
        )
        if should_break:
            phrases.append(current)
            current = []
            current_chars = 0
        current.append(word)
        current_chars += len(token) + (1 if len(current) > 1 else 0)
        if re.search(r"[.!?\u061f\u06d4\u060c,:;]$", token):
            phrases.append(current)
            current = []
            current_chars = 0
    if current:
        phrases.append(current)

    index = 0
    while index < len(phrases) - 1:
        current_phrase = phrases[index]
        next_phrase = phrases[index + 1]
        current_start = float(current_phrase[0]["start_seconds"])
        current_end = max(float(word["end_seconds"]) for word in current_phrase)
        next_start = min(float(word["start_seconds"]) for word in next_phrase)
        gap_seconds = max(0.0, next_start - current_end)
        minimum_hold = 0.5 + 0.3 * len(current_phrase)
        merged = current_phrase + next_phrase
        merged_chars = sum(len(str(word.get("text") or "")) for word in merged) + max(0, len(merged) - 1)
        if (
            current_end - current_start < minimum_hold
            and gap_seconds <= 0.65
            and len(merged) <= max_words
            and merged_chars <= max_chars
        ):
            phrases[index] = merged
            del phrases[index + 1]
            continue
        index += 1
    return phrases


def build_karaoke_caption_markup(
    words: list[dict[str, Any]],
    *,
    overlay_id: str = "captions",
    rtl: bool = False,
    bottom_percent: int = 36,
) -> tuple[str, str]:
    """Build safe timed phrase markup and scene-local GSAP word-highlight instructions."""
    phrases = group_caption_phrases(words)
    markup: list[str] = []
    timeline: list[str] = []
    direction = "rtl" if rtl else "ltr"
    for phrase_index, phrase in enumerate(phrases):
        if not phrase:
            continue
        phrase_start = min(float(word["start_seconds"]) for word in phrase)
        phrase_end = max(float(word["end_seconds"]) for word in phrase)
        duration = max(phrase_end - phrase_start, 0.5 + 0.3 * len(phrase))
        phrase_id = f"{overlay_id}-phrase-{phrase_index + 1}"
        spans = []
        for word_index, word in enumerate(phrase):
            word_id = f"{phrase_id}-word-{word_index + 1}"
            token = html.escape(str(word.get("text") or ""), quote=True)
            spans.append(f'<span id="{word_id}" class="caption-word">{token}</span>')
            word_start = max(0.0, float(word["start_seconds"]))
            word_end = max(word_start + 0.025, float(word["end_seconds"]))
            timeline.append(
                f'tl.set("#{word_id}", {{color:"#ffd76b"}}, {word_start:.4f});'
                f'tl.set("#{word_id}", {{color:"#ffffff"}}, {word_end:.4f});'
            )
        content = " ".join(spans)
        markup.append(
            f'<div id="{phrase_id}" class="clip caption-phrase" dir="{direction}" '
            f'data-start="{phrase_start:.4f}" data-duration="{duration:.4f}" '
            f'data-track-index="30" data-layout-ignore>{content}</div>'
        )
    css = (
        '<style>'
        f'.caption-phrase{{position:absolute;left:7%;right:7%;bottom:{bottom_percent}%;z-index:90;'
        'padding:18px 24px;border-radius:18px;background:rgba(5,10,18,.82);'
        'font-family:"Noto Sans",sans-serif;'
        'font-size:clamp(28px,3.4vw,52px);font-weight:800;line-height:1.45;'
        'text-align:center;text-shadow:0 2px 5px rgba(0,0,0,.9);'
        f'unicode-bidi:isolate;direction:{direction}}}'
        '.caption-word{display:inline;color:#fff;unicode-bidi:isolate;padding:0 .04em}'
        '</style>'
    )
    return css + "".join(markup), "".join(timeline)


def build_episode_lip_envelope(
    audio_assets: list[dict[str, Any]],
    *,
    total_duration: float,
    slot_seconds: float,
    fps: int = 60,
) -> list[float]:
    """Merge each scene's real 60 Hz mouth envelope into one continuous episode timeline."""
    frame_count = max(0, int(round(max(0.0, total_duration) * fps)))
    output = [0.0] * frame_count
    if frame_count == 0 or fps <= 0 or slot_seconds <= 0:
        return output

    speech_start = min(1.05, slot_seconds * 0.16)
    for scene_index, asset in enumerate(audio_assets):
        if not isinstance(asset, dict):
            continue
        samples = asset.get("lip_envelope")
        if not isinstance(samples, list):
            continue
        try:
            scene_speech_start = float(asset.get("speech_start_seconds", speech_start))
        except (TypeError, ValueError):
            scene_speech_start = speech_start
        offset = int(round((scene_index * slot_seconds + scene_speech_start) * fps))
        for sample_index, raw_value in enumerate(samples):
            target = offset + sample_index
            if target >= frame_count:
                break
            try:
                level = max(0.0, min(1.0, float(raw_value)))
            except (TypeError, ValueError):
                continue
            output[target] = max(output[target], level)
    return output

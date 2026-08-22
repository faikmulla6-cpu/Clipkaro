import asyncio
from difflib import SequenceMatcher
import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Any
from app.core.config import get_settings
from .video import ffmpeg_available, find_media_tool
from .caption_layout import build_caption_cards, validate_cards
from .caption_styles import get_caption_style
from .crop_tracking import ffmpeg_focus_expression

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
BUNDLED_DEVANAGARI_FONT = FONT_DIR / "NotoSansDevanagari.ttf"
logger = logging.getLogger("clipkaro.rendering")


def subtitle_ass_filter(ass_path: str | Path, fonts_path: str | Path) -> str:
    """Build a cross-platform FFmpeg ASS filter using absolute escaped paths."""
    def escaped(path: str | Path) -> str:
        return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"ass=filename='{escaped(ass_path)}':fontsdir='{escaped(fonts_path)}'"


def format_srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def timed_words(segments: list[dict[str, Any]], clip_start: float, clip_end: float,
                allow_synthetic: bool = False) -> list[dict[str, Any]]:
    """Return aligned words. Synthetic timing is opt-in and never used by production export."""
    result: list[dict[str, Any]] = []
    for segment in segments:
        words = [word for word in segment.get("words", []) if str(word.get("text", "")).strip()]
        if words:
            for word in words:
                raw_start, raw_end = float(word["start"]), float(word["end"])
                # A native word may differ from the container boundary by a
                # few milliseconds after FFmpeg/FFprobe rounding.  Do not
                # broadly clamp bad provider timing into a plausible caption.
                tolerance = .05
                if raw_start < clip_start - tolerance or raw_end > clip_end + tolerance:
                    continue
                start = max(raw_start, clip_start)
                end = min(raw_end, clip_end)
                if end > start:
                    result.append({"start": start, "end": end, "text": str(word.get("display_text") or word["text"]).strip(),
                                   "confidence": float(word.get("confidence", 1))})
            continue
        if not allow_synthetic:
            continue
        start, end = max(float(segment["start"]), clip_start), min(float(segment["end"]), clip_end)
        tokens = re.sub(r"\s+", " ", str(segment["text"])).strip().split()
        if end <= start or not tokens: continue
        span = (end - start) / len(tokens)
        result.extend({"start": start + index * span, "end": min(end, start + (index + 1) * span),
                       "text": token, "confidence": 0.5}
                      for index, token in enumerate(tokens))
    return sorted(result, key=lambda item: (item["start"], item["end"]))


def _write_word_srt(words: list[dict[str, Any]], path: Path, offset: float = 0) -> None:
    rows = [f"{index}\n{format_srt_time(float(word['start'])-offset)} --> "
            f"{format_srt_time(float(word['end'])-offset)}\n{word['text']}\n"
            for index, word in enumerate(words, 1)]
    path.write_text("\n".join(rows), encoding="utf-8")


def create_srt(segments: list[dict[str, Any]], clip_start: float, clip_end: float, path: Path) -> None:
    _write_word_srt(timed_words(segments, clip_start, clip_end), path, clip_start)


def create_edited_srt(text: str, duration: float, path: Path,
                      reference_words: list[dict[str, Any]] | None = None,
                      clip_start: float = 0) -> None:
    """Keep correction text attached to the closest original audio word timestamps."""
    edited = re.sub(r"\s+", " ", text).strip().split()
    if not edited or duration <= 0:
        path.write_text("", encoding="utf-8")
        return
    reference = reference_words or []
    if not reference:
        span = duration / len(edited)
        aligned = [{"start": index * span, "end": min(duration, (index + 1) * span), "text": word}
                   for index, word in enumerate(edited)]
        _write_word_srt(aligned, path)
        return
    original_tokens = [re.sub(r"\W+", "", str(word["text"]), flags=re.UNICODE).casefold() for word in reference]
    edited_tokens = [re.sub(r"\W+", "", word, flags=re.UNICODE).casefold() for word in edited]
    exact: dict[int, int] = {}
    for block in SequenceMatcher(None, original_tokens, edited_tokens, autojunk=False).get_matching_blocks():
        for delta in range(block.size): exact[block.b + delta] = block.a + delta
    aligned = []
    for index, word in enumerate(edited):
        mapped = exact.get(index)
        if mapped is None:
            mapped = round(index * (len(reference) - 1) / max(1, len(edited) - 1))
        source = reference[max(0, min(mapped, len(reference) - 1))]
        aligned.append({"start": float(source["start"]) - clip_start,
                        "end": float(source["end"]) - clip_start, "text": word})
    # Corrections may add words; guarantee monotonic non-zero events without moving matched audio anchors.
    for index in range(1, len(aligned)):
        if aligned[index]["start"] < aligned[index - 1]["start"]:
            aligned[index]["start"] = aligned[index - 1]["start"]
        if aligned[index]["end"] <= aligned[index]["start"]:
            aligned[index]["end"] = min(duration, aligned[index]["start"] + .12)
    _write_word_srt(aligned, path)


def _srt_seconds(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def _read_srt_cards(path: Path) -> list[tuple[float, float, str]]:
    cards = []
    pattern = re.compile(
        r"(?:^|\n)\d+\s*\n(\d\d:\d\d:\d\d[,.]\d{3})\s*-->\s*"
        r"(\d\d:\d\d:\d\d[,.]\d{3})\s*\n(.+?)(?=\n\s*\n|\Z)", re.S,
    )
    for match in pattern.finditer(path.read_text(encoding="utf-8-sig")):
        text = re.sub(r"\s+", " ", match.group(3)).strip()
        if text:
            cards.append((_srt_seconds(match.group(1)), _srt_seconds(match.group(2)), text))
    return cards


def _ass_time(seconds: float) -> str:
    centis = max(0, int(round(seconds * 100)))
    hours, rem = divmod(centis, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def _ass_safe(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _ass_color(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return "&H00FFFFFF"
    return f"&H00{value[4:6]}{value[2:4]}{value[:2]}".upper()


def _caption_font(text: str, requested: str) -> tuple[str, Path, bool]:
    """Resolve a real local font directory and expose fallback through safe logs.

    Production images install Noto + Liberation from the OS package manager.
    This avoids shipping font binaries in the source artifact while keeping
    Devanagari coverage and an Arial-compatible sans face available to LibASS.
    """
    devanagari = bool(re.search(r"[\u0900-\u097f]", text))
    if os.name == "nt":
        directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        if devanagari and (directory / "NirmalaB.ttf").exists():
            return "Nirmala UI", directory, True
        if requested.casefold() == "arial" and (directory / "arialbd.ttf").exists():
            return "Arial", directory, False

    noto_dir = Path("/usr/share/fonts/truetype/noto")
    liberation_dir = Path("/usr/share/fonts/truetype/liberation2")
    if devanagari and (noto_dir / "NotoSansDevanagari-Bold.ttf").exists():
        return "Noto Sans Devanagari", noto_dir, requested.casefold() != "noto sans devanagari"
    if devanagari and (noto_dir / "NotoSansDevanagari-Regular.ttf").exists():
        return "Noto Sans Devanagari", noto_dir, requested.casefold() != "noto sans devanagari"
    if requested.casefold() == "arial" and liberation_dir.exists():
        return "Liberation Sans", liberation_dir, True
    if BUNDLED_DEVANAGARI_FONT.exists():
        return "Noto Sans Devanagari", FONT_DIR, requested.casefold() != "noto sans devanagari"
    # LibASS/fontconfig can still resolve the requested family globally. The
    # directory is only an optional source of extra font files.
    return requested, FONT_DIR, False


def _india_pop_word_width(text: str, font_size: int) -> float:
    """Stable Arial-like width estimate used only to position visual word cards.

    LibASS does not expose text measurements.  The same deterministic estimate is
    used for every word in a card, while LibASS performs the real glyph drawing.
    """
    narrow = set("I1L.,:;!'| ")
    wide = set("MW@%#")
    units = sum(.36 if char.upper() in narrow else 1.02 if char.upper() in wide else .66 for char in text)
    return max(font_size * .45, units * font_size)


def _india_pop_round_rect(width: int, height: int, radius: int) -> str:
    """ASS vector path for the active-word rounded orange pill."""
    radius = max(1, min(radius, width // 2, height // 2))
    # Cubic Beziers approximate the four rounded corners.  This is drawn by
    # LibASS behind the active word, rather than pretending a colour tag is a
    # browser-style word background.
    return (
        f"m {radius} 0 l {width - radius} 0 "
        f"b {width - radius // 2} 0 {width} {radius // 2} {width} {radius} "
        f"l {width} {height - radius} "
        f"b {width} {height - radius // 2} {width - radius // 2} {height} {width - radius} {height} "
        f"l {radius} {height} "
        f"b {radius // 2} {height} 0 {height - radius // 2} 0 {height - radius} "
        f"l 0 {radius} b 0 {radius // 2} {radius // 2} 0 {radius} 0"
    )


def _caption_y_center(height: int, style: dict[str, Any], caption_position: str) -> int:
    """Resolve the creator's vertical caption choice identically for every style."""
    if caption_position == "center":
        return height // 2
    if caption_position == "above":
        return round(height * float(style["above_safe_ratio"]))
    return round(height * (1 - float(style["bottom_safe_ratio"])))


def _build_india_pop_ass(words: list[dict[str, Any]], ass: Path, width: int, height: int,
                         style: dict[str, Any], caption_position: str,
                         font_name: str | None) -> None:
    """Render India Pop as word-positioned text plus a real active-word pill.

    Generic karaoke ASS tags can recolour a word but cannot create a tight,
    padded, rounded word background.  India Pop uses explicit vector-drawn
    background events and separate word events, preserving the original SRT
    word timing while matching the Creator Studio's visual primitives.
    """
    size = max(18, round(width * float(style["font_size_width_ratio"])))
    normal = _ass_color(str(style["text_color"]))
    outline = _ass_color(str(style["outline_color"]))
    active = _ass_color(str(style["highlight_color"]))
    pill = _ass_color(str(style["highlight_background"]))
    border = max(1, round(width * float(style["outline_width_width_ratio"])))
    inset = round(width * float(style["horizontal_inset_ratio"]))
    resolved_font = font_name or str(style["font_family"])
    y_center = _caption_y_center(height, style, caption_position)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: IndiaPop,{resolved_font},{size},{normal},{normal},{outline},&H00000000,-1,0,0,0,100,100,0,0,1,{border},2,5,{inset},{inset},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    cards = build_caption_cards(words, max_chars=int(style["max_line_width"]),
                                max_words=int(style["words_per_chunk"]),
                                max_duration=float(style["max_duration"]))
    errors = validate_cards(cards, max_chars=int(style["max_line_width"]))
    if any("overflow" in error or "invalid_time" in error for error in errors):
        raise RuntimeError("Caption layout failed safe-area validation; review the transcript before export.")
    events: list[str] = []
    gap = max(7, round(size * .16))
    padding_x = max(9, round(size * .20))
    padding_y = max(7, round(size * .16))
    pill_height = round(size * 1.18) + padding_y * 2
    radius = max(int(style.get("corner_radius_px", 12)), round(size * .22))
    for card in cards:
        display_words = [str(item["text"]).upper() for item in card.words]
        widths = [_india_pop_word_width(value, size) for value in display_words]
        total_width = sum(widths) + gap * max(0, len(widths) - 1)
        # The India Pop card policy is deliberately 1--3 words.  The only
        # fallback is a two-line safety split for an unusually long token.
        split_at = len(display_words)
        if total_width > width - inset * 2 and len(display_words) > 1:
            split_at = 1 if len(display_words) == 2 else 2
        lines = [(0, split_at)]
        if split_at < len(display_words):
            lines.append((split_at, len(display_words)))
        positions: dict[int, tuple[float, float]] = {}
        for line_number, (first, last) in enumerate(lines):
            line_width = sum(widths[first:last]) + gap * max(0, last - first - 1)
            cursor = (width - line_width) / 2
            line_y = y_center + (line_number - (len(lines) - 1) / 2) * round(size * float(style["line_height"]))
            for item_index in range(first, last):
                positions[item_index] = (cursor + widths[item_index] / 2, line_y)
                cursor += widths[item_index] + gap
        for active_index, item in enumerate(card.words):
            start = float(item["start"])
            end = float(card.words[active_index + 1]["start"]) if active_index + 1 < len(card.words) else card.end
            end = max(float(item["end"]), end)
            if end <= start:
                continue
            center_x, center_y = positions[active_index]
            pill_width = round(widths[active_index] + padding_x * 2)
            pill_left = round(center_x - pill_width / 2)
            pill_top = round(center_y - pill_height / 2)
            drawing = _india_pop_round_rect(pill_width, pill_height, radius)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},IndiaPop,,0,0,0,,"
                f"{{\\an7\\pos({pill_left},{pill_top})\\p1\\1c{pill}\\bord0\\shad0}}{drawing}"
            )
            for word_index, value in enumerate(display_words):
                word_x, word_y = positions[word_index]
                colour = active if word_index == active_index else normal
                events.append(
                    f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},IndiaPop,,0,0,0,,"
                    f"{{\\an5\\pos({round(word_x)},{round(word_y)})\\1c{colour}}}{_ass_safe(value)}"
                )
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def _build_studio_personality_ass(words: list[dict[str, Any]], ass: Path, width: int, height: int,
                                  style_id: str, style: dict[str, Any], caption_position: str,
                                  font_name: str | None) -> None:
    """Render the non-India-Pop Studio personalities with their own primitives.

    This intentionally does not use the legacy colour-only karaoke renderer:
    Clean has a card and lime word emphasis, Bold has an orange active block,
    Minimal has a restrained card plus underline, and Kinetic remains bare
    heavyweight type with a lime active word.
    """
    size = max(18, round(width * float(style["font_size_width_ratio"])))
    normal = _ass_color(str(style["text_color"]))
    outline = _ass_color(str(style["outline_color"]))
    active = _ass_color(str(style["highlight_color"]))
    highlight_background = _ass_color(str(style["highlight_background"]))
    border = max(1, round(width * float(style["outline_width_width_ratio"])))
    inset = round(width * float(style["horizontal_inset_ratio"]))
    font = font_name or str(style["font_family"])
    shadow = 3 if style_id == "kinetic" else 4 if style_id == "bold" else 0
    back = outline if style_id in {"kinetic", "bold"} else "&H00000000"
    y_center = _caption_y_center(height, style, caption_position)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Studio,{font},{size},{normal},{normal},{outline},{back},-1,0,0,0,100,100,0,0,1,{border},{shadow},5,{inset},{inset},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    cards = build_caption_cards(words, max_chars=int(style["max_line_width"]),
                                max_words=int(style["words_per_chunk"]),
                                max_duration=float(style["max_duration"]))
    errors = validate_cards(cards, max_chars=int(style["max_line_width"]))
    if any("overflow" in error or "invalid_time" in error for error in errors):
        raise RuntimeError("Caption layout failed safe-area validation; review the transcript before export.")
    events: list[str] = []
    gap = max(5, round(size * .14))
    pad_x = max(7, round(size * .18))
    pad_y = max(5, round(size * .14))
    radius = max(3, int(style.get("corner_radius_px", 0)))
    transform = str(style.get("text_transform") or "none")
    for card in cards:
        display_words = [str(item["text"]).upper() if transform == "uppercase" else str(item["text"])
                         for item in card.words]
        widths = [_india_pop_word_width(value, size) for value in display_words]
        first_count = len(card.lines[0].split()) if len(card.lines) == 2 else len(display_words)
        lines = [(0, first_count)]
        if first_count < len(display_words):
            lines.append((first_count, len(display_words)))
        positions: dict[int, tuple[float, float]] = {}
        card_width = 0.0
        for line_number, (first, last) in enumerate(lines):
            line_width = sum(widths[first:last]) + gap * max(0, last - first - 1)
            card_width = max(card_width, line_width)
            cursor = (width - line_width) / 2
            line_y = y_center + (line_number - (len(lines) - 1) / 2) * round(size * float(style["line_height"]))
            for word_index in range(first, last):
                positions[word_index] = (cursor + widths[word_index] / 2, line_y)
                cursor += widths[word_index] + gap
        card_height = round(size * (1 + (len(lines) - 1) * float(style["line_height"]))) + pad_y * 2
        card_left = round((width - card_width) / 2 - pad_x)
        card_top = round(y_center - card_height / 2)
        card_shape = _india_pop_round_rect(round(card_width + pad_x * 2), card_height, radius)
        for active_index, item in enumerate(card.words):
            start = float(item["start"])
            end = float(card.words[active_index + 1]["start"]) if active_index + 1 < len(card.words) else card.end
            end = max(float(item["end"]), end)
            if end <= start:
                continue
            if style_id == "clean":
                # White Studio card, followed by its compact lime active-word block.
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Studio,,0,0,0,,{{\\an7\\pos({card_left},{card_top})\\p1\\1c&H00FFFFFF\\bord0\\shad0}}{card_shape}")
            elif style_id == "minimal":
                # CSS rgba(0,0,0,.66) maps to ASS transparency 0x57.
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Studio,,0,0,0,,{{\\an7\\pos({card_left},{card_top})\\p1\\1c&H57000000\\bord0\\shad0}}{card_shape}")
            active_x, active_y = positions[active_index]
            if style_id in {"clean", "bold"}:
                active_width = round(widths[active_index] + pad_x * 1.25)
                active_height = round(size * 1.08 + pad_y * 1.2)
                active_left = round(active_x - active_width / 2)
                active_top = round(active_y - active_height / 2)
                events.append(
                    f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Studio,,0,0,0,,"
                    f"{{\\an7\\pos({active_left},{active_top})\\p1\\1c{highlight_background}\\bord0\\shad0}}"
                    f"{_india_pop_round_rect(active_width, active_height, radius)}"
                )
            elif style_id == "minimal":
                underline_width = max(8, round(widths[active_index]))
                underline_height = max(2, round(size * .075))
                # The Studio's Minimal preview deliberately keeps the text
                # white and uses ClipKaro lime only for the thin underline.
                underline_colour = _ass_color("#DFFF57")
                events.append(
                    f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Studio,,0,0,0,,"
                    f"{{\\an7\\pos({round(active_x - underline_width / 2)},{round(active_y + size * .49)})\\p1\\1c{underline_colour}\\bord0\\shad0}}"
                    f"m 0 0 l {underline_width} 0 l {underline_width} {underline_height} l 0 {underline_height}"
                )
            for word_index, value in enumerate(display_words):
                word_x, word_y = positions[word_index]
                colour = active if word_index == active_index else normal
                # Clean's highlighted word remains its canonical dark green;
                # Bold uses white on orange; Kinetic uses lime; Minimal white.
                if style_id == "bold" and word_index == active_index:
                    colour = active
                events.append(
                    f"Dialogue: 2,{_ass_time(start)},{_ass_time(end)},Studio,,0,0,0,,"
                    f"{{\\an5\\pos({round(word_x)},{round(word_y)})\\1c{colour}}}{_ass_safe(value)}"
                )
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def _build_ass(srt: Path, ass: Path, width: int, height: int, caption_style: str,
               caption_position: str, font_name: str | None = None) -> None:
    words = [{"start": s, "end": e, "text": t} for s, e, t in _read_srt_cards(srt)]
    style = get_caption_style(caption_style)
    if caption_style == "hindi-pop":
        _build_india_pop_ass(words, ass, width, height, style, caption_position, font_name)
        return
    if caption_style in {"kinetic", "clean", "bold", "minimal"}:
        _build_studio_personality_ass(words, ass, width, height, caption_style, style, caption_position, font_name)
        return
    size = max(18, round(width * float(style["font_size_width_ratio"])))
    normal = _ass_color(str(style["text_color"]))
    outline = _ass_color(str(style["outline_color"]))
    active = _ass_color(str(style["highlight_color"]))
    border = max(1, round(width * float(style["outline_width_width_ratio"])))
    background = str(style.get("background") or "")
    border_style = 3 if background != "transparent" else 1
    back = "&H60000000" if "0,0,0" in background else "&H20FFFFFF" if "255,255,255" in background else "&H00000000"
    alignment = 5 if caption_position == "center" else 2
    margin_v = 0 if caption_position == "center" else round(height * float(style["above_safe_ratio"] if caption_position == "above" else style["bottom_safe_ratio"]))
    inset = round(width * float(style["horizontal_inset_ratio"]))
    transform = str(style.get("text_transform") or "none")
    resolved_font = font_name or str(style["font_family"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{resolved_font},{size},{normal},{normal},{outline},{back},-1,0,0,0,100,100,0,0,{border_style},{border},0,{alignment},{inset},{inset},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    cards = build_caption_cards(words, max_chars=int(style["max_line_width"]), max_words=int(style["words_per_chunk"]), max_duration=float(style["max_duration"]))
    errors = validate_cards(cards, max_chars=int(style["max_line_width"]))
    if any("overflow" in error or "invalid_time" in error for error in errors):
        raise RuntimeError("Caption layout failed safe-area validation; review the transcript before export.")
    for card in cards:
        card_end = card.end
        card_texts = [str(item["text"]).upper() if transform == "uppercase" else str(item["text"]) for item in card.words]
        for index, item in enumerate(card.words):
            word_start, word_end = float(item["start"]), float(item["end"])
            state_end = float(card.words[index + 1]["start"]) if index + 1 < len(card.words) else card_end
            state_end = max(word_end, state_end)
            styled_words = [
                f"{{\\c{active}}}{_ass_safe(value)}{{\\c{normal}}}" if item_index == index else _ass_safe(value)
                for item_index, value in enumerate(card_texts)
            ]
            first_count = len(card.lines[0].split()) if len(card.lines) == 2 else len(styled_words)
            styled = " ".join(styled_words[:first_count])
            if len(card.lines) == 2: styled += r"\N" + " ".join(styled_words[first_count:])
            events.append(f"Dialogue: 0,{_ass_time(word_start)},{_ass_time(state_end)},Caption,,0,0,0,,{styled}")
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def _drawtext_safe(text: str, limit: int) -> str:
    # Avoid shell/path quoting entirely. Curly apostrophes are visually equivalent
    # and do not terminate FFmpeg's single-quoted drawtext value on Windows.
    return (text.replace("\\", "")
                .replace("'", "’")
                .replace(":", "\\:")
                .replace(",", "\\,")
                .replace("\n", " "))[:limit]


def _font_option(text: str = "") -> str:
    configured = os.getenv("CAPTION_FONT_FILE", "").strip()
    candidates = [configured] if configured else []
    devanagari = bool(re.search(r"[\u0900-\u097f]", text))
    if os.name == "nt":
        windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        if devanagari:
            candidates.extend(str(windows / name) for name in ("NirmalaB.ttf", "Nirmala.ttf"))
        candidates.append(str(windows / "arial.ttf"))
    else:
        if devanagari:
            candidates.extend((
                "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            ))
        candidates.extend((
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ))
    # Local developer builds may still have the optional historical bundled
    # fallback; release packaging intentionally excludes font binaries.
    if devanagari:
        candidates.append(str(BUNDLED_DEVANAGARI_FONT))
    path = next((Path(item) for item in candidates if item and Path(item).exists()), None)
    if not path: return ""
    escaped = str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f":fontfile='{escaped}'"


async def render_short(source: Path, output: Path, start: float, end: float, srt: Path | None,
                       hook: str, watermark: bool, resolution: str = "720p", aspect_ratio: str = "9:16",
                       caption_style: str = "kinetic", brand_text: str = "",
                       primary_color: str = "#DFFF57", focus_x: float = 50,
                       caption_position: str = "bottom",
                       crop_keyframes: list[dict[str, float]] | None = None,
                       source_caption_band: float | None = None) -> None:
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg and FFprobe are required to export video.")
    ffmpeg, ffprobe = find_media_tool("ffmpeg"), find_media_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and FFprobe are installed but not runnable. Reinstall the correct Windows build.")
    settings = get_settings()
    process_timeout = max(30, int(settings.media_process_timeout_seconds))
    ffmpeg_threads = max(1, int(settings.media_ffmpeg_threads))
    sizes = {
        ("720p", "9:16"): (720, 1280), ("1080p", "9:16"): (1080, 1920),
        ("720p", "1:1"): (720, 720), ("1080p", "1:1"): (1080, 1080),
        ("720p", "4:5"): (720, 900), ("1080p", "4:5"): (1080, 1350),
    }
    width, height = sizes[(resolution, aspect_ratio)]
    focus = max(0.0, min(float(focus_x), 100.0)) / 100.0
    focus_expression = ffmpeg_focus_expression(crop_keyframes, end-start) if crop_keyframes else f"{focus:.3f}"
    filters = [
        # ASS/SRT events are clip-local.  Output seeking alone leaves source
        # timestamps intact on some FFmpeg builds, which makes captions at
        # 00:00--00:30 disappear for a clip cut from later in the source.
        "setpts=PTS-STARTPTS",
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}:(iw-{width})*{focus_expression}:(ih-{height})/2",
    ]
    hook_words = hook.split()[:8]
    safe_hook = _drawtext_safe(" ".join(hook_words), 72)
    hook_size = max(26, min(max(30, width // 18), int(width * .84 / max(1, len(safe_hook) * .54))))
    hex_color = primary_color.lstrip("#")
    if safe_hook:
        filters.append(f"drawtext=text='{safe_hook}'{_font_option(safe_hook)}:expansion=none:fontcolor=white:fontsize={hook_size}:box=1:boxcolor=black@0.68:boxborderw=14:x=(w-text_w)/2:y=h*0.10:enable='between(t,0,4.5)'")
    ass: Path | None = None
    if srt and srt.exists() and _read_srt_cards(srt):
        output.parent.mkdir(parents=True, exist_ok=True)
        ass = output.with_suffix(".ass")
        style = get_caption_style(caption_style)
        source_text = " ".join(card[2] for card in _read_srt_cards(srt))
        resolved_font, font_dir, fallback_used = _caption_font(source_text, str(style["font_family"]))
        logger.info("caption_style_render style=%s requested_font=%s resolved_font=%s font_fallback_used=%s", caption_style, style["font_family"], resolved_font, fallback_used)
        _build_ass(srt, ass, width, height, caption_style, caption_position, resolved_font)
        # Pass an explicitly escaped absolute path.  On Windows, FFmpeg's ASS
        # filter can resolve a basename against the source instead of its cwd,
        # silently producing a valid-looking export with no caption overlay.
        filters.append(subtitle_ass_filter(ass.resolve(), font_dir.resolve()))
    # Product watermark and creator Brand Kit are separate concepts. Free-plan
    # watermarking must not overwrite a creator's own wordmark, and paid users
    # may remove ClipKaro branding while deliberately keeping their brand mark.
    if watermark:
        product_mark = "ClipKaro AI"
        filters.append(
            f"drawtext=text='{product_mark}'{_font_option(product_mark)}:expansion=none:"
            f"fontcolor=0xDFFF57@0.92:fontsize={max(18,width//35)}:box=1:"
            "boxcolor=black@0.30:boxborderw=8:x=w-tw-24:y=24"
        )
    safe_brand = _drawtext_safe(brand_text, 40)
    if safe_brand:
        filters.append(
            f"drawtext=text='{safe_brand}'{_font_option(safe_brand)}:expansion=none:"
            f"fontcolor=0x{hex_color}@0.96:fontsize={max(18,width//35)}:box=1:"
            "boxcolor=black@0.34:boxborderw=8:x=24:y=24"
        )
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            # Input seeking gives the filter graph a clip-local timeline.  With
            # output seeking, ASS subtitle events could be evaluated against
            # the original source timestamp and vanish on later clips.
            [ffmpeg, "-nostdin", "-threads", str(ffmpeg_threads), "-y", "-ss", str(start), "-i", str(source.resolve()),
             "-t", str(end-start), "-vf", ",".join(filters), "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(output.resolve())],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
            cwd=str(output.parent.resolve()), timeout=process_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        if ass: ass.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Video render exceeded the {process_timeout}-second safety limit.") from exc
    if ass: ass.unlink(missing_ok=True)
    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        stderr = proc.stderr.decode(errors="ignore")
        useful = [line.strip() for line in stderr.splitlines() if any(
            token in line.lower() for token in ("error", "failed", "invalid", "unable", "no such")
        )]
        detail = " | ".join(useful[-5:]) or "\n".join(stderr.splitlines()[-12:])
        raise RuntimeError(f"Video render failed: {detail[-1400:]}")
    try:
        probe = await asyncio.to_thread(
            subprocess.run,
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,width,height:format=duration,size", "-of", "json", str(output.resolve())],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=min(60, process_timeout),
        )
    except subprocess.TimeoutExpired as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError("Rendered video validation timed out.") from exc
    try:
        import json
        payload = json.loads(probe.stdout.decode("utf-8", errors="ignore"))
        rendered_duration = float(payload.get("format", {}).get("duration", 0))
        rendered_size = int(payload.get("format", {}).get("size", 0))
        has_video = bool(payload.get("streams"))
    except (ValueError, TypeError, json.JSONDecodeError):
        rendered_duration, rendered_size, has_video = 0.0, 0, False
    expected = end - start
    if probe.returncode != 0 or not has_video or rendered_size < 10_000 or rendered_duration < max(1.0, expected * .9):
        output.unlink(missing_ok=True)
        raise RuntimeError("Video render failed validation because the source ended early or is incomplete. Upload the complete original MP4 and retry.")
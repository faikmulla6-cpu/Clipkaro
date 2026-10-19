"""Place v2 subtitles on the split seam only during actual two-person shots.

ASS Dialogues are split at camera cuts, including when Smart Edit removes or
reorders footage. The input subtitle file remains private, in the same worker
scratch directory as the export. The existing caption style is preserved.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

_ASS = re.compile(r"^(\d+):(\d{2}):(\d{2})[.](\d{2})$")
_PREFIX = re.compile(r"^((?:\{[^{}]*\})*)")
_POSITION = re.compile(r"\\pos\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")
_TEXT_ANCHOR = re.compile(r"\\an5(?!\d)")
_DRAWING = re.compile(r"\\p[1-9](?!\d)")


def _seconds(value: str) -> float:
    matched = _ASS.fullmatch(value)
    if not matched:
        raise ValueError("Invalid ASS event timestamp")
    hours, minute, second, centisec = [int(s) for s in matched.groups()]
    return hours * 3600 + minute * 60 + second + centisec / 100


def _format(value: float) -> str:
    centisec = max(0, round(value*100))
    hours, remainder = divmod(centisec,360000)
    minutes, remainder = divmod(remainder,6000)
    seconds, cs = divmod(remainder,100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def _regions(scenes: list[dict], edit_ranges: list[dict] | None) -> list[tuple[float,float,str]]:
    source_ranges = edit_ranges or [{"start":0., "end":float(scenes[-1]["end"])}]
    mapped = []
    destination_time = 0.0
    for piece in source_ranges:
        a, b = float(piece["start"]),float(piece["end"])
        if a < 0 or b <= a:
            raise ValueError("Unsafe Smart Edit caption interval")
        for scene in scenes:
            overlap_start = max(a,float(scene["start"]))
            overlap_end = min(b,float(scene["end"]))
            if overlap_end - overlap_start <= .005:
                continue
            mapped.append((destination_time + overlap_start-a,
                           destination_time + overlap_end-a,
                           scene["caption_zone"]))
        destination_time += b-a
    return sorted(mapped)


def _positioned_text_y(text: str) -> float | None:
    """Only inspect ASS overrides, never the customer's spoken text."""
    prefix = _PREFIX.match(text).group(1)
    position = _POSITION.search(prefix)
    if position and _TEXT_ANCHOR.search(prefix) and not _DRAWING.search(prefix):
        return float(position.group(2))
    return None


def _move_to_middle(text: str, delta_y: float, center_x: int,
                    center_y: int) -> str:
    prefix = _PREFIX.match(text).group(1)
    position = _POSITION.search(prefix)
    if position:
        # India Pop has individual words anchored at their centers (\an5)
        # and separate coloured vector-pill backgrounds anchored top-left
        # (\an7). Move BOTH with one delta, preserving every original tag.
        shifted_y = round(float(position.group(2)) + delta_y)
        new_position = f"\\pos({position.group(1)},{shifted_y})"
        return (prefix[:position.start()] + new_position + prefix[position.end():]
                + text[len(prefix):])
    # Plain legacy ASS subtitles have no absolute position to translate.
    # Insert a SINGLE centered position without affecting colours or timing.
    return f"{{\\an5\\pos({center_x},{center_y})}}" + text


def position_ass_by_scene(path: Path, scenes: list[dict], output_width: int,
                          output_height: int, edit_ranges: list[dict] | None) -> None:
    """Keep solo captions low; move complete Dual Stack cards to the seam.

    Split each dialogue event at the camera/Smart Edit boundaries. A caption
    card's text and its separately drawn active-word highlight share exact
    ASS Start/End values, so shift the whole card as one visual unit. Merely
    APPENDING a second \pos after the first is unreliable in libass, and was
    the cause of subtitles covering the lower speaker in customer exports.
    """
    if not scenes or not any(s["caption_zone"] == "middle" for s in scenes):
        return
    regions = _regions(scenes, edit_ranges)
    if not regions:
        return
    contents = path.read_text(encoding="utf-8-sig")
    rows: list[str | list[str]] = []
    centered: dict[tuple[str, str, str], list[list[str]]] = defaultdict(list)

    for line in contents.splitlines(keepends=True):
        if not line.startswith("Dialogue:"):
            rows.append(line)
            continue
        fields = line.rstrip("\r\n").split(",", 9)
        if len(fields) != 10:
            raise ValueError("Unexpected ASS subtitle record")
        start, end = _seconds(fields[1]), _seconds(fields[2])
        if end <= start:
            continue
        for region_start, region_end, zone in regions:
            a, b = max(start, region_start), min(end, region_end)
            if b - a < .015:
                continue
            part = fields.copy()
            part[1], part[2] = _format(a), _format(b)
            rows.append(part)
            if zone == "middle":
                centered[(part[1], part[2], part[3])].append(part)

    for group in centered.values():
        # One word-state emits multiple text events, and often a vector
        # background. Text positions define the card's actual vertical
        # center; using the pill's top-left would shift it incorrectly.
        text_ys = [_positioned_text_y(fields[9]) for fields in group]
        text_ys = [value for value in text_ys if value is not None]
        shift_y = (
            output_height / 2 - (min(text_ys) + max(text_ys)) / 2
            if text_ys else 0.
        )
        for fields in group:
            fields[9] = _move_to_middle(
                fields[9], shift_y, output_width // 2, output_height // 2
            )

    path.write_text("".join(
        row if isinstance(row, str) else ",".join(row) + "\n"
        for row in rows
    ), encoding="utf-8-sig")

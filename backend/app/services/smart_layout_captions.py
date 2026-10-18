"""Place v2 subtitles on the split seam only during actual two-person shots.

ASS Dialogues are split at camera cuts, including when Smart Edit removes or
reorders footage. The input subtitle file remains private, in the same worker
scratch directory as the export. The existing caption style is preserved.
"""
from __future__ import annotations

import re
from pathlib import Path

_ASS = re.compile(r"^(\d+):(\d{2}):(\d{2})[.](\d{2})$")
_PREFIX = re.compile(r"^((?:\{[^{}]*\})*)")


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


def position_ass_by_scene(path: Path, scenes: list[dict], output_width: int,
                          output_height: int, edit_ranges: list[dict] | None) -> None:
    """Rewrite ASS events without touching language/style/watermark.

    Captions crossing a camera cut are split at the cut, so only the dual-shot
    portion is relocated to the central divider.
    """
    if not scenes or not any(scene["caption_zone"]=="middle" for scene in scenes):
        return
    regions = _regions(scenes,edit_ranges)
    if not regions:
        return
    contents = path.read_text(encoding="utf-8-sig")
    output = []
    middle_tag = r"{\an5\pos("+str(output_width//2)+","+str(output_height//2)+")}"
    for line in contents.splitlines(keepends=True):
        if not line.startswith("Dialogue:"):
            output.append(line)
            continue
        head = line.rstrip("\r\n").split(",",9)
        if len(head) != 10:
            raise ValueError("Unexpected ASS subtitle record")
        a = _seconds(head[1])
        b = _seconds(head[2])
        if b <= a:
            continue
        parts = []
        for region_start,region_end,zone in regions:
            x = max(a,region_start)
            y = min(b,region_end)
            if y-x >= .015:
                segment = head.copy()
                segment[1],segment[2] = _format(x),_format(y)
                if zone=="middle":
                    prefix = _PREFIX.match(segment[9]).group(1)
                    # Position tag after any existing style overrides, so it
                    # wins against old user-authored bottom position overrides.
                    segment[9] = prefix+middle_tag+segment[9][len(prefix):]
                parts.append(",".join(segment)+"\n")
        if parts:
            output.extend(parts)
        else:
            # A subtitle not in retained footage cannot be remapped to an
            # arbitrary scene: drop it, rather than show captions on wrong faces.
            continue
    path.write_text("".join(output),encoding="utf-8-sig")

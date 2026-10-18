"""Versioned, private Smart Layout timeline contract shared by preview and export.

This module is deliberately pure: it cannot fetch user media, access the
database, request external APIs, charge quotas, or create an export. It accepts
ONLY a plan already produced by Clipkaro's own private media analyzer.

All coordinates are source pixel rectangles, not CSS percentages. In
particular, an unverified one-person shot can NEVER become two panels.
"""
from __future__ import annotations

import math
from typing import Any

VERSION = 2
MAX_SCENES = 24
MAX_CLIP_SECONDS = 180.0
MAX_SOURCE_EDGE = 16384
PREVIEW_WIDTH = 360
PREVIEW_HEIGHT = 640
MODES = frozenset(("auto", "dual_stack", "speaker_focus"))
SCENE_LAYOUTS = frozenset(("wide", "single", "speaker_focus", "dual_stack"))


class UnsafeLayoutPlan(ValueError):
    """The plan cannot safely be displayed or rendered."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise UnsafeLayoutPlan(name + " must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise UnsafeLayoutPlan(name + " must be numeric") from exc
    if not math.isfinite(number):
        raise UnsafeLayoutPlan(name + " must be finite")
    return number


def _bounded(value: Any, minimum: float, maximum: float, name: str) -> float:
    number = _finite(value, name)
    if not minimum <= number <= maximum:
        raise UnsafeLayoutPlan(name + " is outside its allowed range")
    return number


def _rect(x: float, y: float, w: float, h: float, source_w: int,
          source_h: int) -> list[int]:
    if min(x, y) < 0 or w < 2 or h < 2:
        raise UnsafeLayoutPlan("Crop rectangle is invalid")
    left, top, width, height = [int(round(n)) for n in (x, y, w, h)]
    if left + width > source_w or top + height > source_h:
        raise UnsafeLayoutPlan("Crop rectangle extends beyond the source")
    return [left, top, width, height]


def _center(center: Any) -> tuple[float, float]:
    if not isinstance(center, (tuple, list)) or len(center) < 2:
        raise UnsafeLayoutPlan("Face center must have x and y")
    return (_bounded(center[0], 0, 1, "face x"),
            _bounded(center[1], 0, 1, "face y"))


def _person_crop(source_w: int, source_h: int,
                 center: tuple[float, float]) -> list[int]:
    # Matches the crop geometry in karo_smart_layouts._focus_expression.
    width = min(source_w, int(source_h * 9 / 16)) // 2 * 2
    height = min(source_h, int(width * 16 / 9)) // 2 * 2
    if width < 2 or height < 2:
        raise UnsafeLayoutPlan("Source is too small for a person crop")
    cx, cy = _center(center)
    x = round(max(0, min(source_w - width, cx * source_w - width / 2)))
    y = round(max(0, min(source_h - height, cy * source_h - .43 * height)))
    return _rect(x, y, width, height, source_w, source_h)


def _dual_crop(source_w: int, source_h: int,
               center: tuple[float, float], other_x: float,
               target_w: int, half_height: int) -> list[int]:
    cx, cy = _center(center)
    gap = abs(other_x - cx)
    maximum = max(2, int(source_w * max(.30, min(.55, gap * .98))))
    aspect = target_w / half_height
    width = min(source_w, int(source_h * aspect), maximum) // 2 * 2
    height = min(source_h, int(width / aspect)) // 2 * 2
    if width < 2 or height < 2:
        raise UnsafeLayoutPlan("Invalid dual-panel dimensions")
    x = round(max(0, min(source_w - width, cx * source_w - width / 2)))
    y = round(max(0, min(source_h - height, cy * source_h - .43 * height)))
    return _rect(x, y, width, height, source_w, source_h)


def _transitions(raw: Any, length: float, count: int) -> list[list[float | int]]:
    if not isinstance(raw, (tuple, list)) or len(raw) > 42:
        raise UnsafeLayoutPlan("Invalid speaking transitions")
    changes: list[list[float | int]] = []
    previous = -1.0
    for row in raw:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise UnsafeLayoutPlan("Invalid speaking transition")
        time = _bounded(row[0], 0, length + .05, "speaker time")
        who = row[1]
        if type(who) is not int or who < 0 or who >= count or time < previous:
            raise UnsafeLayoutPlan("Invalid speaker order or reference")
        previous = time
        changes.append([round(time, 3), who])
    return changes


def from_media_plan(plan: Any, *, source_start: float,
                    duration: float, target_width: int = PREVIEW_WIDTH,
                    target_height: int = PREVIEW_HEIGHT) -> dict[str, Any]:
    """Serialize the EXACT approved per-shot analyzer plan for a preview.

    No face inference, filesystem reads, or layout invention happens here.
    The request's source clip offset is encoded explicitly; the scene
    timestamps remain local to the clip, like the existing FFmpeg graph.
    """
    mode = getattr(plan, "mode", None)
    if mode not in MODES:
        raise UnsafeLayoutPlan("Unknown Smart Layout mode")
    w = getattr(plan, "width", None)
    h = getattr(plan, "height", None)
    if type(w) is not int or type(h) is not int or not (240 <= w <= MAX_SOURCE_EDGE and
                                                      160 <= h <= MAX_SOURCE_EDGE):
        raise UnsafeLayoutPlan("Invalid source dimensions")
    start = _bounded(source_start, 0, 86400, "source start")
    total = _bounded(duration, .10, MAX_CLIP_SECONDS, "clip duration")
    if not (target_width == 360 and target_height == 640):
        raise UnsafeLayoutPlan("Unsupported preview coordinate space")
    scenes = getattr(plan, "segments", ())
    if not isinstance(scenes, (tuple, list)) or not (1 <= len(scenes) <= MAX_SCENES):
        raise UnsafeLayoutPlan("A bounded scene timeline is required")

    output: list[dict[str, Any]] = []
    last_end = 0.0
    for entry in scenes:
        a = _bounded(getattr(entry, "start", None), 0, total, "scene start")
        b = _bounded(getattr(entry, "end", None), 0, total + .01, "scene end")
        kind = getattr(entry, "mode", None)
        if kind not in SCENE_LAYOUTS or b - a < .03 or abs(a - last_end) > .065:
            raise UnsafeLayoutPlan("The scene timeline has an invalid gap, overlap or mode")
        centers = tuple(_center(point) for point in getattr(entry, "centers", ()))
        if len(centers) > 2:
            raise UnsafeLayoutPlan("Only two visible primary speakers supported")

        panel_height = (target_height * 12 // 100) // 2 * 2
        half = (target_height - panel_height) // 2
        if kind == "dual_stack":
            if len(centers) != 2 or centers[1][0] - centers[0][0] < .16:
                raise UnsafeLayoutPlan("Cannot split without two separate faces")
            panels = [
                _dual_crop(w, h, centers[0], centers[1][0], target_width, half),
                _dual_crop(w, h, centers[1], centers[0][0], target_width, half),
            ]
        elif kind in ("single", "speaker_focus"):
            if not centers:
                raise UnsafeLayoutPlan("Cannot focus without a detected face")
            panels = [_person_crop(w, h, center) for center in centers]
        else:
            panels = [[0, 0, w, h]]
        transitions = _transitions(getattr(entry, "switches", ()), b - a, len(panels))
        if kind != "speaker_focus" and transitions:
            raise UnsafeLayoutPlan("Speaker transitions are only valid for focus scenes")
        output.append({
            "start": round(a, 3),
            "end": round(b, 3),
            "layout": kind,
            "crops": panels,
            "switches": transitions,
            "caption_zone": "middle" if kind == "dual_stack" else "bottom",
        })
        last_end = b
    if abs(last_end - total) > .065:
        raise UnsafeLayoutPlan("The scene timeline does not cover the clip")

    return {
        "version": VERSION,
        "requested_mode": mode,
        "source_width": w,
        "source_height": h,
        "source_start": round(start, 3),
        "duration": round(total, 3),
        "preview_width": target_width,
        "preview_height": target_height,
        "scenes": output,
    }


def scene_at(payload: dict[str, Any], relative_time: float) -> dict[str, Any] | None:
    """Return a trusted plan's scene at a clip-relative playback timestamp."""
    t = _finite(relative_time, "playhead")
    for scene in payload.get("scenes", []):
        if scene["start"] <= t < scene["end"]:
            return scene
    return None

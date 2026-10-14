"""Non-destructive Smart Edit timing shared by preview and export."""

from __future__ import annotations

import re
from typing import Any


FILLERS = {"uh", "um", "erm", "hmm", "ah", "like", "basically", "actually"}
MIN_RANGE = 0.04
MIN_KEEP = 0.25


def empty_edit_plan() -> dict[str, Any]:
    return {"version": 2, "removed_ranges": [], "split_points": [], "segment_order": [0]}


def _logical_segments(split_points: list[float], duration: float) -> list[dict[str, float]]:
    boundaries = [0.0, *split_points, duration]
    return [
        {"start": boundaries[index], "end": boundaries[index + 1]}
        for index in range(len(boundaries) - 1)
        if boundaries[index + 1] - boundaries[index] >= MIN_RANGE
    ]


def _normalise_segment_order(raw: Any, count: int) -> list[int]:
    natural = list(range(count))
    if not isinstance(raw, list) or len(raw) != count:
        return natural
    try:
        order = [int(value) for value in raw]
    except (TypeError, ValueError):
        return natural
    if sorted(order) != natural:
        return natural
    return order


def normalize_edit_plan(value: Any, duration: float) -> dict[str, Any]:
    """Validate, clamp and merge a user-authored edit plan."""
    source = value if isinstance(value, dict) else {}
    ranges: list[dict[str, Any]] = []
    for item in source.get("removed_ranges", []):
        if not isinstance(item, dict):
            continue
        try:
            start = max(0.0, min(float(item["start"]), duration))
            end = max(0.0, min(float(item["end"]), duration))
        except (KeyError, TypeError, ValueError):
            continue
        if end - start < MIN_RANGE:
            continue
        reason = str(item.get("reason") or "manual")[:24]
        ranges.append({"start": start, "end": end, "reason": reason})
    ranges.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[dict[str, Any]] = []
    for item in ranges:
        if merged and item["start"] <= merged[-1]["end"] + .001:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            if merged[-1]["reason"] != item["reason"]:
                merged[-1]["reason"] = "mixed"
        else:
            merged.append(dict(item))

    points: list[float] = []
    for raw in source.get("split_points", []):
        try:
            point = float(raw)
        except (TypeError, ValueError):
            continue
        if .05 < point < duration - .05 and not any(abs(point - old) < .02 for old in points):
            points.append(point)
    points.sort()

    if sum(item["end"] - item["start"] for item in merged) >= duration - MIN_KEEP:
        raise ValueError("Smart Edit must keep at least 0.25 seconds of the clip.")

    segments = _logical_segments(points, duration)
    segment_order = _normalise_segment_order(source.get("segment_order"), len(segments))
    return {
        "version": 2,
        "removed_ranges": [
            {**item, "start": round(item["start"], 3), "end": round(item["end"], 3)}
            for item in merged
        ],
        "split_points": [round(point, 3) for point in points],
        "segment_order": segment_order,
    }


def plan_reorders_segments(plan: dict[str, Any], duration: float) -> bool:
    normal = normalize_edit_plan(plan, duration)
    natural = list(range(len(_logical_segments(normal["split_points"], duration))))
    return normal["segment_order"] != natural


def _segment_kept_ranges(
    segment: dict[str, float],
    removed_ranges: list[dict[str, Any]],
) -> list[dict[str, float]]:
    start, end = float(segment["start"]), float(segment["end"])
    cursor = start
    output: list[dict[str, float]] = []
    for cut in removed_ranges:
        cut_start = max(start, float(cut["start"]))
        cut_end = min(end, float(cut["end"]))
        if cut_end <= start or cut_start >= end:
            continue
        if cut_start > cursor + MIN_RANGE:
            output.append({"start": round(cursor, 3), "end": round(cut_start, 3)})
        cursor = max(cursor, cut_end)
        if cursor >= end:
            break
    if end > cursor + MIN_RANGE:
        output.append({"start": round(cursor, 3), "end": round(end, 3)})
    return output


def kept_ranges(plan: dict[str, Any], duration: float) -> list[dict[str, float]]:
    """Return kept source ranges in final output order.

    Split points define logical segments. segment_order can reorder those
    segments while all removals/trims inside each segment stay non-destructive.
    """
    normal = normalize_edit_plan(plan, duration)
    segments = _logical_segments(normal["split_points"], duration)
    output: list[dict[str, float]] = []
    for segment_index in normal["segment_order"]:
        for piece in _segment_kept_ranges(segments[segment_index], normal["removed_ranges"]):
            if output and abs(output[-1]["end"] - piece["start"]) < .001:
                output[-1]["end"] = piece["end"]
            else:
                output.append(piece)
    return output


def source_to_output_time(source_time: float, plan: dict[str, Any], duration: float) -> float | None:
    elapsed = 0.0
    for item in kept_ranges(plan, duration):
        if item["start"] <= source_time <= item["end"]:
            return elapsed + source_time - item["start"]
        elapsed += item["end"] - item["start"]
    return None


def apply_plan_to_words(words: list[dict[str, Any]], plan: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    normal = normalize_edit_plan(plan, duration)
    output: list[dict[str, Any]] = []
    for word in words:
        start, end = float(word["start"]), float(word["end"])
        if any(start < cut["end"] and end > cut["start"] for cut in normal["removed_ranges"]):
            continue
        mapped_start = source_to_output_time(start, normal, duration)
        mapped_end = source_to_output_time(end, normal, duration)
        if mapped_start is None or mapped_end is None or mapped_end <= mapped_start:
            continue
        output.append({
            **word,
            "source_start": start,
            "source_end": end,
            "start": round(mapped_start, 3),
            "end": round(mapped_end, 3),
        })
    output.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    return output


def clean_speech_ranges(words: list[dict[str, Any]], duration: float, min_pause: float = .45) -> list[dict[str, Any]]:
    """Suggest conservative filler, silence and immediate repeated-start cuts."""
    suggestions: list[dict[str, Any]] = []
    previous = None
    for word in sorted(words, key=lambda item: float(item["start"])):
        start, end = float(word["start"]), float(word["end"])
        token = re.sub(r"[^\w']", "", str(word.get("text") or "").casefold())
        if previous and start - float(previous["end"]) >= min_pause:
            suggestions.append({"start": float(previous["end"]), "end": start, "reason": "silence"})
        if token in FILLERS:
            suggestions.append({"start": start, "end": end, "reason": "filler"})
        if previous:
            old = re.sub(r"[^\w']", "", str(previous.get("text") or "").casefold())
            if token and token == old and start - float(previous["end"]) < .35:
                suggestions.append({
                    "start": float(previous["start"]),
                    "end": float(previous["end"]),
                    "reason": "repeat",
                })
        previous = word
    return normalize_edit_plan({"removed_ranges": suggestions}, duration)["removed_ranges"]

"""Non-destructive Smart Edit timing shared by preview and export."""

from __future__ import annotations

import re
from typing import Any


FILLERS = {"uh", "um", "erm", "hmm", "ah", "like", "basically", "actually"}
MIN_RANGE = 0.04


def empty_edit_plan() -> dict[str, Any]:
    return {"version": 1, "removed_ranges": [], "split_points": []}


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
    if sum(item["end"] - item["start"] for item in merged) >= duration - .25:
        raise ValueError("Smart Edit must keep at least 0.25 seconds of the clip.")
    return {
        "version": 1,
        "removed_ranges": [{**item, "start": round(item["start"], 3), "end": round(item["end"], 3)} for item in merged],
        "split_points": [round(point, 3) for point in sorted(points)],
    }


def kept_ranges(plan: dict[str, Any], duration: float) -> list[dict[str, float]]:
    cursor, output = 0.0, []
    for item in normalize_edit_plan(plan, duration)["removed_ranges"]:
        if item["start"] > cursor + MIN_RANGE:
            output.append({"start": round(cursor, 3), "end": round(item["start"], 3)})
        cursor = max(cursor, item["end"])
    if duration > cursor + MIN_RANGE:
        output.append({"start": round(cursor, 3), "end": round(duration, 3)})
    return output


def source_to_output_time(source_time: float, plan: dict[str, Any], duration: float) -> float | None:
    elapsed = 0.0
    for item in kept_ranges(plan, duration):
        if source_time < item["start"]:
            return elapsed
        if item["start"] <= source_time <= item["end"]:
            return elapsed + source_time - item["start"]
        elapsed += item["end"] - item["start"]
    return None


def apply_plan_to_words(words: list[dict[str, Any]], plan: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for word in words:
        start, end = float(word["start"]), float(word["end"])
        if any(start < cut["end"] and end > cut["start"] for cut in plan.get("removed_ranges", [])):
            continue
        mapped_start = source_to_output_time(start, plan, duration)
        mapped_end = source_to_output_time(end, plan, duration)
        if mapped_start is None or mapped_end is None or mapped_end <= mapped_start:
            continue
        output.append({**word, "source_start": start, "source_end": end,
                       "start": round(mapped_start, 3), "end": round(mapped_end, 3)})
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
                suggestions.append({"start": float(previous["start"]), "end": float(previous["end"]), "reason": "repeat"})
        previous = word
    return normalize_edit_plan({"removed_ranges": suggestions}, duration)["removed_ranges"]

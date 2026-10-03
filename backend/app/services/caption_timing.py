from __future__ import annotations

from typing import Any


def speech_regions_from_segments(segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Read the persisted source-level speech mask without inventing timing."""
    for segment in segments:
        raw = segment.get("speech_regions")
        if not isinstance(raw, list):
            continue
        regions: list[dict[str, float]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
            except (TypeError, ValueError):
                continue
            if end > start >= 0:
                regions.append({"start": start, "end": end})
        return sorted(regions, key=lambda item: (item["start"], item["end"]))
    return []


def clip_speech_regions(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
) -> list[dict[str, float | int]]:
    """Return clip-relative speech intervals with stable source-region ids."""
    output: list[dict[str, float | int]] = []
    for region_id, region in enumerate(speech_regions_from_segments(segments)):
        start = max(float(region["start"]), clip_start)
        end = min(float(region["end"]), clip_end)
        if end <= start:
            continue
        output.append({
            "id": region_id,
            "start": round(start - clip_start, 3),
            "end": round(end - clip_start, 3),
        })
    return output


def reconcile_caption_words(
    words: list[dict[str, Any]],
    speech_regions: list[dict[str, float]],
    clip_start: float,
    clip_end: float,
) -> list[dict[str, Any]]:
    """Clamp visual word timing to real speech while preserving transcript truth."""
    relevant = [
        (region_id, max(float(region["start"]), clip_start), min(float(region["end"]), clip_end))
        for region_id, region in enumerate(speech_regions)
        if float(region["end"]) > clip_start and float(region["start"]) < clip_end
    ]
    if not relevant:
        return sorted(words, key=lambda item: (float(item["start"]), float(item["end"])))

    output: list[dict[str, Any]] = []
    for source in words:
        word = dict(source)
        start = float(word["start"])
        end = float(word["end"])
        overlaps = [
            (min(end, region_end) - max(start, region_start), region_id, region_start, region_end)
            for region_id, region_start, region_end in relevant
            if min(end, region_end) > max(start, region_start)
        ]
        if overlaps:
            _, region_id, region_start, region_end = max(overlaps, key=lambda item: item[0])
            gated_start = max(start, region_start)
            gated_end = min(end, region_end)
            if gated_end > gated_start:
                word["start"] = round(gated_start, 3)
                word["end"] = round(gated_end, 3)
                word["speech_region_id"] = region_id
                word["speech_aligned"] = True
        output.append(word)

    ordered = sorted(output, key=lambda item: (float(item["start"]), float(item["end"])))
    for index in range(len(ordered) - 1):
        current = ordered[index]
        following = ordered[index + 1]
        current_region = current.get("speech_region_id")
        if (
            current_region is not None
            and current_region == following.get("speech_region_id")
            and float(following["start"]) > float(current["end"])
        ):
            current["end"] = round(float(following["start"]), 3)
    return ordered

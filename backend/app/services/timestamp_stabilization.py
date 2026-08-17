from typing import Any


def stabilize_word_timestamps(segments: list[dict[str, Any]], min_word_duration: float = .08,
                              max_boundary_error: float = .35) -> list[dict[str, Any]]:
    """Stable-TS-inspired monotonic cleanup after ASR quality/consensus gates.

    This never invents missing words. It only clamps accepted aligned words to their
    utterance, resolves small overlaps at their midpoint, and rejects large conflicts.
    """
    output: list[dict[str, Any]] = []
    previous_end = 0.0
    for segment in segments:
        seg_start, seg_end = float(segment["start"]), float(segment["end"])
        clean: list[dict[str, Any]] = []
        for source in segment.get("words", []):
            start, end = float(source.get("start", -1)), float(source.get("end", -1))
            if end <= start or start < seg_start - max_boundary_error or end > seg_end + max_boundary_error:
                continue
            start, end = max(start, seg_start, previous_end), min(end, seg_end)
            if clean and start < float(clean[-1]["end"]):
                overlap = float(clean[-1]["end"]) - start
                if overlap > max_boundary_error: continue
                midpoint = (float(clean[-1]["end"]) + start) / 2
                clean[-1]["end"], start = midpoint, midpoint
            if end - start < min_word_duration:
                end = min(seg_end, start + min_word_duration)
            if end <= start: continue
            clean.append({**source, "start": round(start, 3), "end": round(end, 3),
                          "timing_stabilized": True})
            previous_end = end
        if clean:
            output.append({**segment, "start": clean[0]["start"], "end": clean[-1]["end"],
                           "words": clean, "alignment_status": "native_stabilized",
                           "alignment_backend": "whisper_native"})
    return output

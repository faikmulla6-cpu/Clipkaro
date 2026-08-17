import re
from typing import Any


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w\u0900-\u097f]+", text.casefold(), re.UNICODE))


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Token-level Levenshtein error; measures insertions/deletions hidden by character similarity."""
    left, right = normalize(reference).split(), normalize(hypothesis).split()
    if not left: return 0.0 if not right else 1.0
    previous = list(range(len(right) + 1))
    for index, token in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(min(previous[other_index] + 1, current[-1] + 1,
                               previous[other_index - 1] + (token != other)))
        previous = current
    return previous[-1] / len(left)


def transcript_agreement(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> dict[str, Any]:
    left = normalize(" ".join(str(s.get("text", "")) for s in primary))
    right = normalize(" ".join(str(s.get("text", "")) for s in secondary))
    wer = word_error_rate(left, right)
    score = max(0.0, 1.0 - wer)
    return {"accepted": score >= .64, "score": round(score, 3),
            "word_error_rate": round(wer, 3)}


def attach_provenance(segments: list[dict[str, Any]], provider: str, model: str,
                      agreement: float | None = None) -> list[dict[str, Any]]:
    for segment in segments:
        segment["asr_provider"] = provider
        segment["asr_model"] = model
        if segment.get("agreement_score") is None: segment["agreement_score"] = agreement
        segment["review_required"] = bool(segment.get("review_required", False))
    return segments


def verify_segments(primary: list[dict[str, Any]], secondary: list[dict[str, Any]],
                    threshold: float = .58) -> dict[str, Any]:
    """Verify each primary utterance against overlapping independent ASR output."""
    verified, rejected = [], []
    total_duration = sum(max(0, float(s["end"]) - float(s["start"])) for s in primary)
    for segment in primary:
        overlaps = [other for other in secondary
                    if max(float(segment["start"]), float(other["start"])) <
                       min(float(segment["end"]), float(other["end"]))]
        comparison = transcript_agreement([segment], overlaps)
        row = {**segment, "agreement_score": comparison["score"],
               "review_required": comparison["score"] < threshold}
        (verified if not row["review_required"] else rejected).append(row)
    verified_duration = sum(max(0, float(s["end"]) - float(s["start"])) for s in verified)
    coverage = verified_duration / max(total_duration, .01)
    return {"accepted": bool(verified) and verified_duration >= 20 and coverage >= .6,
            "segments": verified, "rejected": rejected, "coverage": round(coverage, 3)}

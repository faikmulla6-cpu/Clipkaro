import hashlib
import json
from typing import Any

PIPELINE_VERSION = "7.8.0"
PIPELINE_COMPONENTS = {
    "asr": "faster-whisper-medium+small-conditional-wer-v4",
    "alignment": "honest-native-or-whisperx-forced-v3",
    "captions": "hinglish-phrase-layout-v3",
    "source_caption_scan": "tesseract-hin-eng-band-mask-v2",
    "media_runtime": "validated-ffmpeg-windows-v2",
    "ranking": "multilingual-density-overlap-v2",
}
PIPELINE_FINGERPRINT = hashlib.sha256(
    json.dumps(PIPELINE_COMPONENTS, sort_keys=True).encode()
).hexdigest()[:16]


def stamp_segments(segments: list[dict[str, Any]], origin: str = "asr") -> list[dict[str, Any]]:
    for segment in segments:
        segment["pipeline_version"] = PIPELINE_VERSION
        segment["pipeline_fingerprint"] = PIPELINE_FINGERPRINT
        segment["transcript_origin"] = origin
    return segments


def transcript_state(segments: list[dict[str, Any]], require_consensus: bool = True,
                     require_forced_alignment: bool = False) -> dict[str, Any]:
    if not segments:
        return {"current": False, "export_safe": False, "reason": "missing_transcript"}
    current = all(s.get("pipeline_version") == PIPELINE_VERSION and
                  s.get("pipeline_fingerprint") == PIPELINE_FINGERPRINT for s in segments)
    if not current:
        return {"current": False, "export_safe": False, "reason": "stale_pipeline"}
    asr = [s for s in segments if s.get("transcript_origin") == "asr"]
    if require_consensus and asr and any(float(s.get("agreement_score") or 0) < .58 for s in asr):
        return {"current": True, "export_safe": False, "reason": "missing_consensus"}
    accepted_alignment = {"forced_aligned"} if require_forced_alignment else {"native_stabilized", "forced_aligned"}
    if asr and any(s.get("alignment_status") not in accepted_alignment or not s.get("words") for s in asr):
        return {"current": True, "export_safe": False, "reason": "missing_alignment"}
    result = {"current": True, "export_safe": True, "reason": "verified"}
    if asr:
        result["alignment_mode"] = "forced" if all(
            s.get("alignment_status") == "forced_aligned" for s in asr
        ) else "native"
    return result

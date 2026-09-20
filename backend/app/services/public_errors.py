from __future__ import annotations

"""Stable, user-safe messages for heavy media failures.

Provider/FFmpeg exceptions can contain absolute paths, upstream response text or
other operational detail that belongs in server logs rather than persisted API
objects. These helpers intentionally expose only actionable product-level
messages while callers retain the original exception in structured logs.
"""


def _normalized(exc: BaseException) -> str:
    return " ".join(str(exc).strip().lower().split())


def safe_project_failure(exc: BaseException) -> str:
    raw = _normalized(exc)
    if "no complete 20" in raw and "moment" in raw:
        return "We found speech, but no complete 20–90 second moments. Try a longer source video."
    if "transcript quality verification" in raw or "insufficient reliable speech" in raw:
        return (
            "Not enough clear speech was detected. ClipKaro needs at least 20 seconds of reliable spoken dialogue "
            "to find a 20–90 second Short. Try a video with more audible speech."
        )
    if "source video" in raw and ("expired" in raw or "unavailable" in raw or "storage" in raw):
        return "The source video is no longer available. Upload it again and retry."
    if "quota" in raw or "processing minute" in raw or "karo minute" in raw:
        return "This video exceeds the processing allowance available on your current plan."
    if "duration" in raw and ("limit" in raw or "too long" in raw or "maximum" in raw):
        return "This source video is longer than the maximum duration supported by your current plan."
    if "security scan" in raw or "clamav" in raw or "malware" in raw:
        return "ClipKaro could not safely accept this video. Try a different source file."
    if "ffprobe" in raw or "invalid video" in raw or "unsupported" in raw or "could not probe" in raw:
        return "ClipKaro could not read this video reliably. Try an MP4, MOV, MKV or WebM source."
    if "transcrib" in raw or "asr" in raw or "provider" in raw or "elevenlabs" in raw or "groq" in raw or "cloudflare" in raw:
        return "Transcription is temporarily unavailable for this video. Please retry shortly."
    if "timeout" in raw or "timed out" in raw:
        return "Video processing took too long. Please retry; if it repeats, try a shorter source."
    return "ClipKaro could not finish processing this video. Please retry."


def safe_export_failure(exc: BaseException) -> str:
    raw = _normalized(exc)
    if "source video" in raw and ("expired" in raw or "unavailable" in raw or "storage" in raw):
        return "The source video is no longer available. Upload it again to create a new export."
    if "timestamp" in raw or "caption" in raw:
        return "This clip does not have safe caption timing for export. Re-analyse the source and retry."
    if "ffmpeg" in raw or "render" in raw or "encode" in raw:
        return "ClipKaro could not render this Short. Please retry the export."
    if "timeout" in raw or "timed out" in raw:
        return "This export took too long. Please retry; if it repeats, shorten the clip."
    return "ClipKaro could not finish this export. Please retry."

import asyncio
import math
import json
import shutil
import subprocess
from pathlib import Path
from fastapi import HTTPException, UploadFile
from app.core.config import get_settings

ALLOWED_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/matroska"}
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
GENERIC_UPLOAD_TYPES = {
    "",
    "application/octet-stream",
    "application/x-matroska",
    "application/matroska",
}


def find_media_tool(name: str) -> str | None:
    """Return a runnable FFmpeg-family binary, not a Windows alias or corrupt file."""
    candidates: list[str] = []
    discovered = shutil.which(name)
    if discovered:
        candidates.append(discovered)
    # GitHub-hosted Ubuntu and minimal production images normally expose these
    # tools under /usr/bin. Keep an explicit fallback so an isolated Python
    # virtualenv cannot accidentally hide the system media binaries from tests.
    for location in (Path("/usr/bin") / name, Path("/usr/local/bin") / name):
        if location.is_file() and str(location) not in candidates:
            candidates.append(str(location))
    for candidate in candidates:
        try:
            probe = subprocess.run(
                [candidate, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return candidate
    return None


def ffmpeg_available() -> bool:
    return find_media_tool("ffmpeg") is not None and find_media_tool("ffprobe") is not None


def upload_type_supported(filename: str | None, content_type: str | None) -> bool:
    """Treat extension + FFprobe as authoritative, not unreliable browser MIME.

    Browsers and Windows commonly report MKV (and some MOV files) as an empty,
    generic octet-stream, or application Matroska type. A known supported
    extension is required; generic/known video MIME is accepted and the
    processing pipeline's FFprobe check remains the real content validation
    step. Clearly non-video MIME is rejected early.
    """
    ext = Path(filename or "").suffix.lower()
    mime = (content_type or "").strip().lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False
    if mime in GENERIC_UPLOAD_TYPES or mime in ALLOWED_TYPES:
        return True
    return mime.startswith("video/")


async def save_upload(file: UploadFile, destination: Path) -> int:
    settings = get_settings()
    if not upload_type_supported(file.filename, file.content_type):
        raise HTTPException(415, "Only MP4, MOV, WebM, and MKV videos are supported.")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(413, f"Video exceeds the {settings.max_upload_mb} MB plan limit.")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return total


async def probe_metadata(path: Path) -> dict[str, float | int]:
    ffprobe = find_media_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError(
            "FFmpeg and FFprobe were not found. Install FFmpeg, add its bin folder to Windows PATH, then restart both PowerShell windows."
        )
    settings = get_settings()
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration:stream=width,height",
             "-of", "json", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=min(60, max(10, int(settings.media_process_timeout_seconds))),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(422, "The uploaded video took too long to inspect and was rejected for safety.") from exc
    if proc.returncode != 0:
        raise HTTPException(422, "The uploaded video could not be read. It may be corrupted.")
    try:
        payload = json.loads(proc.stdout)
        stream = (payload.get("streams") or [{}])[0]
        duration = float(payload["format"]["duration"])
        width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("FFprobe could not read video duration and dimensions. Convert the source to a standard H.264 MP4 and try again.") from exc
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("The video has no readable picture stream or duration. Try exporting it again as H.264 MP4 with AAC audio.")
    return {"duration": duration, "width": width, "height": height}


async def probe_duration(path: Path) -> float:
    return float((await probe_metadata(path))["duration"])


async def probe_audio_duration(path: Path) -> float:
    ffprobe = find_media_tool("ffprobe")
    if not ffprobe: raise RuntimeError("FFprobe is required for API ASR duration checks.")
    proc = await asyncio.to_thread(subprocess.run, [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30)
    try: duration = float(proc.stdout.decode().strip())
    except ValueError as exc: raise RuntimeError("FFprobe could not read extracted audio duration.") from exc
    if proc.returncode or duration <= 0: raise RuntimeError("Extracted audio is unreadable.")
    return duration

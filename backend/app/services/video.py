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
    candidate = shutil.which(name)
    if not candidate:
        return None
    try:
        probe = subprocess.run([candidate, "-version"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return candidate if probe.returncode == 0 else None


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


async def save_upload(file: UploadFile, destination: Path, *,
                      size_limit_mb: int | None = None) -> int:
    settings = get_settings()
    if not upload_type_supported(file.filename, file.content_type):
        raise HTTPException(415, "Only MP4, MOV, WebM, and MKV videos are supported.")
    limit_mb = int(size_limit_mb or min(settings.max_upload_mb, 500))
    max_bytes = limit_mb * 1024 * 1024
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(413, f"Video exceeds the {limit_mb} MB upload limit.")
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


async def extract_audio(video_path: Path, audio_path: Path) -> None:
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for audio extraction.")
    settings = get_settings()
    timeout = max(30, int(settings.media_process_timeout_seconds))
    threads = max(1, int(settings.media_ffmpeg_threads))
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [ffmpeg, "-nostdin", "-threads", str(threads), "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(audio_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        audio_path.unlink(missing_ok=True)
        raise RuntimeError(f"Audio extraction exceeded the {timeout}-second safety limit.") from exc
    if proc.returncode != 0:
        audio_path.unlink(missing_ok=True)
        raise RuntimeError(f"FFmpeg audio extraction failed: {proc.stderr.decode(errors='ignore')[-500:]}")


async def extract_api_audio(video_path: Path, audio_path: Path) -> None:
    """Losslessly compress 16 kHz mono audio before API upload."""
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg is required for audio extraction.")
    settings = get_settings()
    try:
        proc = await asyncio.to_thread(subprocess.run, [ffmpeg, "-nostdin", "-threads", str(max(1, int(settings.media_ffmpeg_threads))), "-y", "-i", str(video_path), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(audio_path)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False, timeout=max(30, int(settings.media_process_timeout_seconds)))
    except subprocess.TimeoutExpired as exc:
        audio_path.unlink(missing_ok=True); raise RuntimeError("Audio extraction exceeded the safety limit.") from exc
    if proc.returncode:
        audio_path.unlink(missing_ok=True); raise RuntimeError("FFmpeg API audio extraction failed.")


async def chunk_api_audio(audio_path: Path, *, duration: float, output_dir: Path, chunk_seconds: int, overlap_seconds: int, max_chunks: int, max_bytes: int) -> list[tuple[Path, float, float]]:
    """Create chronological FLAC chunks with overlap; never silently truncate."""
    # Provider size limits are necessary but insufficient: APIs can accept a
    # small FLAC that is still longer than the configured safe request span.
    # Split on either condition so long low-complexity audio exercises the
    # overlap/reassembly path instead of becoming one unbounded provider call.
    if audio_path.stat().st_size <= max_bytes and duration <= chunk_seconds:
        return [(audio_path, 0.0, duration)]
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg is required for API ASR chunking.")
    span, overlap = max(30, int(chunk_seconds)), max(0, min(int(overlap_seconds), max(1, int(chunk_seconds // 4))))
    step = span - overlap
    count = math.ceil(max(0.0, duration - overlap) / step)
    if count > max_chunks: raise RuntimeError(f"Audio requires {count} API chunks, exceeding configured safety limit {max_chunks}. Split the source and retry.")
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[tuple[Path, float, float]] = []
    for index in range(count):
        start, length = index * step, min(span, duration - index * step)
        target = output_dir / f"asr-{index:03d}.flac"
        proc = await asyncio.to_thread(subprocess.run, [ffmpeg, "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(audio_path), "-ac", "1", "-ar", "16000", "-c:a", "flac", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False, timeout=max(30, int(get_settings().media_process_timeout_seconds)))
        if proc.returncode or not target.exists(): raise RuntimeError("FFmpeg could not create an API ASR audio chunk.")
        if target.stat().st_size > max_bytes: raise RuntimeError("An API ASR chunk exceeds the configured provider upload limit. Reduce ASR_CHUNK_SECONDS and retry.")
        chunks.append((target, float(start), float(length)))
    return chunks

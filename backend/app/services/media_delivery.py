from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.render_gate import media_encode_slot
from app.services.video import find_media_tool


SOURCE_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}

_BROWSER_SAFE_MP4_VIDEO = {"h264"}
_BROWSER_SAFE_MP4_AUDIO = {None, "aac"}
_BROWSER_SAFE_H264_PIX_FMTS = {"yuv420p", "yuvj420p"}
_BROWSER_SAFE_WEBM_VIDEO = {"vp8", "vp9", "av1"}
_BROWSER_SAFE_WEBM_AUDIO = {None, "opus", "vorbis"}


class MediaToolUnavailable(RuntimeError):
    """Raised when FFmpeg/FFprobe is unavailable for a required preview proxy."""


class MediaPreviewError(RuntimeError):
    """Raised when an uploaded source cannot be converted into a browser preview."""


@dataclass(frozen=True)
class MediaAsset:
    path: Path
    media_type: str
    mode: str


@dataclass(frozen=True)
class StreamProfile:
    video_codec: str
    audio_codec: str | None
    format_name: str
    pixel_format: str | None = None


_lock_loop: asyncio.AbstractEventLoop | None = None
_video_locks: dict[str, asyncio.Lock] = {}


def _suffix(value: str | Path | None) -> str:
    if value is None:
        return ""
    return Path(str(value)).suffix.lower()


def source_media_type(original_filename: str | None, stored_path: str | Path | None = None) -> str:
    """Return the MIME type of the bytes being served, never a fake MP4 type.

    The stored suffix wins because it describes the file actually opened by
    FileResponse. `original_filename` is the fallback for older/migrated rows
    whose storage path may have lost its extension.
    """
    stored_suffix = _suffix(stored_path)
    if stored_suffix in SOURCE_MEDIA_TYPES:
        return SOURCE_MEDIA_TYPES[stored_suffix]
    original_suffix = _suffix(original_filename)
    if original_suffix in SOURCE_MEDIA_TYPES:
        return SOURCE_MEDIA_TYPES[original_suffix]
    return "application/octet-stream"


def source_extension(original_filename: str | None, stored_path: str | Path | None = None) -> str:
    stored_suffix = _suffix(stored_path)
    if stored_suffix in SOURCE_MEDIA_TYPES:
        return stored_suffix
    original_suffix = _suffix(original_filename)
    return original_suffix if original_suffix in SOURCE_MEDIA_TYPES else stored_suffix or original_suffix


def _safe_video_id(video_id: str) -> str:
    # IDs are generated internally, but sanitising here makes the cache path
    # safe even for migrated/imported rows.
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(video_id))[:160] or "video"


def preview_path_for(video_id: str) -> Path:
    return get_settings().storage_root / "previews" / f"{_safe_video_id(video_id)}.mp4"


def _fresh_preview(preview: Path, source: Path) -> bool:
    try:
        return preview.is_file() and preview.stat().st_size > 0 and preview.stat().st_mtime_ns >= source.stat().st_mtime_ns
    except OSError:
        return False


def _video_lock(video_id: str) -> asyncio.Lock:
    """Deduplicate first-time proxy creation without crossing event loops."""
    global _lock_loop, _video_locks
    current = asyncio.get_running_loop()
    if _lock_loop is not current:
        _lock_loop = current
        _video_locks = {}
    return _video_locks.setdefault(video_id, asyncio.Lock())


async def probe_stream_profile(path: Path) -> StreamProfile:
    ffprobe = find_media_tool("ffprobe")
    if not ffprobe:
        raise MediaToolUnavailable("FFprobe is required to prepare a browser-safe video preview.")
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=format_name:stream=codec_type,codec_name,pix_fmt",
                "-of", "json", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaPreviewError("FFprobe timed out while inspecting the uploaded video.") from exc
    except OSError as exc:
        raise MediaToolUnavailable("FFprobe could not be started for browser preview preparation.") from exc

    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="ignore")[-500:].strip()
        raise MediaPreviewError(f"FFprobe could not inspect the uploaded video. {detail}".strip())
    try:
        payload = json.loads(proc.stdout)
        streams = payload.get("streams") or []
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        format_name = str((payload.get("format") or {}).get("format_name") or "")
        return StreamProfile(
            video_codec=str(video.get("codec_name") or "").lower(),
            audio_codec=str(audio.get("codec_name") or "").lower() if audio else None,
            format_name=format_name.lower(),
            pixel_format=str(video.get("pix_fmt") or "").lower() or None,
        )
    except (StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaPreviewError("The uploaded file has no readable video stream for browser preview.") from exc


def _browser_safe_h264(profile: StreamProfile) -> bool:
    return profile.video_codec == "h264" and profile.pixel_format in _BROWSER_SAFE_H264_PIX_FMTS


def _can_serve_direct(extension: str, profile: StreamProfile) -> bool:
    if extension in {".mp4", ".m4v"}:
        return (
            profile.video_codec in _BROWSER_SAFE_MP4_VIDEO
            and _browser_safe_h264(profile)
            and profile.audio_codec in _BROWSER_SAFE_MP4_AUDIO
        )
    if extension == ".webm":
        return profile.video_codec in _BROWSER_SAFE_WEBM_VIDEO and profile.audio_codec in _BROWSER_SAFE_WEBM_AUDIO
    # MOV and MKV are intentionally proxied even when their codecs happen to be
    # browser-compatible because cross-browser container support is inconsistent.
    return False


def _source_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


async def _build_mp4_proxy(source: Path, destination: Path, profile: StreamProfile) -> None:
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise MediaToolUnavailable("FFmpeg is required to prepare this video's browser preview.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.part.mp4")
    start_signature = _source_signature(source)

    command = [
        ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1",
    ]
    if _browser_safe_h264(profile):
        # Browser-safe H.264 in MOV/MKV can be remuxed without re-encoding.
        command += ["-c:v", "copy"]
    else:
        # Standardise incompatible codecs and H.264 chroma/bit-depth variants
        # to conservative 8-bit 4:2:0 H.264 for broad browser decoding.
        command += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        ]
    if profile.audio_codec is None:
        command += ["-an"]
    elif profile.audio_codec == "aac":
        command += ["-c:a", "copy"]
    else:
        command += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    command += ["-movflags", "+faststart", str(temp)]

    try:
        # This is the same gate used by final Short exports. A small deployment
        # never has an export and preview transcode unexpectedly fighting for
        # the same CPU/RAM at render_concurrency=1.
        async with media_encode_slot():
            proc = await asyncio.to_thread(
                subprocess.run,
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
                timeout=max(30, int(get_settings().media_process_timeout_seconds)),
            )
        if proc.returncode != 0:
            detail = proc.stderr.decode(errors="ignore")[-900:].strip()
            raise MediaPreviewError(f"FFmpeg could not create a browser-safe preview. {detail}".strip())
        if not temp.is_file() or temp.stat().st_size <= 0:
            raise MediaPreviewError("FFmpeg finished without creating a usable browser preview.")
        # Never publish a proxy for a source that changed/disappeared while the
        # transform was running (cleanup/delete/replace race).
        if not source.is_file() or _source_signature(source) != start_signature:
            raise FileNotFoundError(str(source))
        output_profile = await probe_stream_profile(temp)
        if not _browser_safe_h264(output_profile) or output_profile.audio_codec not in _BROWSER_SAFE_MP4_AUDIO:
            raise MediaPreviewError("Generated preview did not pass the H.264/AAC browser compatibility check.")
        os.replace(temp, destination)
        if not source.is_file() or _source_signature(source) != start_signature:
            destination.unlink(missing_ok=True)
            raise FileNotFoundError(str(source))
    except subprocess.TimeoutExpired as exc:
        raise MediaPreviewError("Browser preview transcoding exceeded the configured media safety timeout.") from exc
    finally:
        temp.unlink(missing_ok=True)


async def ensure_browser_media(video: dict[str, Any]) -> MediaAsset:
    source = Path(str(video["file_path"]))
    if not source.is_file():
        raise FileNotFoundError(str(source))

    extension = source_extension(video.get("original_filename"), source)
    original_type = source_media_type(video.get("original_filename"), source)
    preview = preview_path_for(str(video["id"]))
    if _fresh_preview(preview, source):
        return MediaAsset(preview, "video/mp4", "cached-proxy")

    profile = await probe_stream_profile(source)
    if _can_serve_direct(extension, profile):
        return MediaAsset(source, original_type, "direct")

    lock = _video_lock(str(video["id"]))
    async with lock:
        if not source.is_file():
            raise FileNotFoundError(str(source))
        if _fresh_preview(preview, source):
            return MediaAsset(preview, "video/mp4", "cached-proxy")
        # A source may have been replaced while this request waited for another
        # request to finish. Re-probe it before deciding how to proxy.
        profile = await probe_stream_profile(source)
        if _can_serve_direct(extension, profile):
            return MediaAsset(source, original_type, "direct")
        await _build_mp4_proxy(source, preview, profile)
        return MediaAsset(preview, "video/mp4", "transcoded-proxy")


def remove_preview_files(video_id: str) -> int:
    directory = get_settings().storage_root / "previews"
    if not directory.exists():
        return 0
    safe_id = _safe_video_id(video_id)
    removed = 0
    for path in [directory / f"{safe_id}.mp4", *directory.glob(f".{safe_id}.*.part.mp4")]:
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError:
            # A response/FFmpeg process can briefly own a file on Windows. The
            # hourly cleanup pass will retry rather than failing all retention.
            continue
    return removed


def remove_orphaned_previews(valid_video_ids: set[str]) -> int:
    directory = get_settings().storage_root / "previews"
    if not directory.exists():
        return 0
    valid = {_safe_video_id(item) for item in valid_video_ids}
    removed = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".mp4") and not name.startswith("."):
            owner = name[:-4]
        elif name.startswith(".") and name.endswith(".part.mp4"):
            owner = name[1:].split(".", 1)[0]
        else:
            continue
        if owner in valid:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed

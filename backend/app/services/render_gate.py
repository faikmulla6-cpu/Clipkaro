from __future__ import annotations

import asyncio
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from app.core.config import get_settings
from .rendering import render_short
from .video import find_media_tool


_loop: asyncio.AbstractEventLoop | None = None
_semaphore: asyncio.Semaphore | None = None
_limit: int | None = None


def _media_encode_semaphore() -> asyncio.Semaphore:
    """Return one FFmpeg encode gate per event loop.

    Preview normalisation and final Short rendering share this exact gate. On a
    small VPS that prevents a first-time MOV/MKV preview transcode from running
    alongside a final export and unexpectedly doubling CPU/RAM pressure.
    """
    global _loop, _semaphore, _limit
    current = asyncio.get_running_loop()
    configured = max(1, int(get_settings().render_concurrency))
    if _loop is not current or _semaphore is None:
        _loop = current
        _limit = configured
        _semaphore = asyncio.Semaphore(configured)
    elif _limit != configured and getattr(_semaphore, "_value", 0) == _limit:
        # Tests/development can change the configured limit. Recreate the gate
        # only while idle so no in-flight encoder loses its reservation.
        _limit = configured
        _semaphore = asyncio.Semaphore(configured)
    return _semaphore


@asynccontextmanager
async def media_encode_slot() -> AsyncIterator[None]:
    semaphore = _media_encode_semaphore()
    async with semaphore:
        yield


def _render_controls_from_keyframes(
    keyframes: list[dict[str, Any]] | None,
) -> tuple[float, bool | None, list[dict[str, Any]]]:
    """Extract private render controls and return only real crop observations."""
    zoom = 1.0
    preserve: bool | None = None
    cleaned: list[dict[str, Any]] = []
    for item in keyframes or []:
        marker_zoom = item.get("zoom")
        marker_preserve = item.get("preserve_source_captions")
        if marker_zoom is not None or marker_preserve is not None:
            if marker_zoom is not None:
                zoom = max(1.0, min(float(marker_zoom), 2.0))
            if marker_preserve is not None:
                preserve = bool(marker_preserve)
            continue
        cleaned.append(item)
    return zoom, preserve, cleaned


def _zoom_from_keyframes(keyframes: list[dict[str, Any]] | None) -> tuple[float, list[dict[str, Any]]]:
    """Backwards-compatible helper retained for focused tests."""
    zoom, _, cleaned = _render_controls_from_keyframes(keyframes)
    return zoom, cleaned


async def _prepare_zoomed_clip(
    source: Path,
    output: Path,
    start: float,
    end: float,
    zoom: float,
    focus_x: float,
) -> Path:
    """Pre-crop the selected interval around the creator's horizontal focus.

    The resulting source keeps the original pixel dimensions. The normal
    renderer then centres its aspect-ratio crop, so zoom and Left/Centre/Right
    behave as one framing control instead of applying the horizontal shift twice.
    Captions, hook text and watermarks are added only after this video-only step.
    """
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for zoomed export.")
    settings = get_settings()
    duration = max(0.1, float(end) - float(start))
    threads = max(1, int(settings.media_ffmpeg_threads))
    timeout = max(30, int(settings.media_process_timeout_seconds))
    temp = output.with_name(f".{output.stem}.zoom-source.mp4")
    temp.unlink(missing_ok=True)
    z = max(1.0, min(float(zoom), 2.0))
    focus = max(0.0, min(float(focus_x), 100.0)) / 100.0
    crop_x = f"(iw-iw/{z:.4f})*{focus:.4f}"
    vf = (
        f"crop=iw/{z:.4f}:ih/{z:.4f}:{crop_x}:(ih-ih/{z:.4f})/2,"
        f"scale=trunc(iw*{z:.4f}/2)*2:trunc(ih*{z:.4f}/2)*2"
    )
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [
                ffmpeg, "-nostdin", "-threads", str(threads), "-y",
                "-ss", str(start), "-i", str(source.resolve()), "-t", str(duration),
                "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temp.resolve()),
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError("Zoom preparation exceeded the media safety limit.") from exc
    if proc.returncode != 0 or not temp.is_file() or temp.stat().st_size < 10_000:
        detail = proc.stderr.decode(errors="ignore")[-1200:]
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"Zoom preparation failed: {detail}")
    return temp


async def render_short_limited(*args: Any, **kwargs: Any) -> None:
    """Bound final Short rendering through the shared FFmpeg encode gate.

    Private render controls travel inside the already-durable crop payload and
    are removed before crop tracking. This keeps local API and isolated worker
    exports behaviorally identical.
    """
    async with media_encode_slot():
        mutable = list(args)
        keyframes = kwargs.get("crop_keyframes")
        if keyframes is None and len(mutable) > 14:
            keyframes = mutable[14]
        zoom, preserve_requested, cleaned_keyframes = _render_controls_from_keyframes(keyframes)
        if "crop_keyframes" in kwargs:
            kwargs = {**kwargs, "crop_keyframes": cleaned_keyframes}
        elif len(mutable) > 14:
            mutable[14] = cleaned_keyframes

        source_caption_band = kwargs.get("source_caption_band")
        if source_caption_band is None and len(mutable) > 15:
            source_caption_band = mutable[15]

        # Detection is advisory; the creator's Preserve source captions toggle
        # is authoritative. If OFF, the renderer must crop/zoom normally even
        # when text was detected near the bottom of the source.
        if preserve_requested is False:
            source_caption_band = None
            if "source_caption_band" in kwargs:
                kwargs = {**kwargs, "source_caption_band": None}
            elif len(mutable) > 15:
                mutable[15] = None
        elif preserve_requested is True and source_caption_band is None:
            source_caption_band = .82
            if "source_caption_band" in kwargs:
                kwargs = {**kwargs, "source_caption_band": source_caption_band}
            elif len(mutable) > 15:
                mutable[15] = source_caption_band

        # A creator explicitly preserving source captions gets the safest full
        # frame and no destructive zoom of the burned-in subtitle band.
        if preserve_requested is True and source_caption_band is not None:
            zoom = 1.0

        if zoom <= 1.001:
            await render_short(*mutable, **kwargs)
            return

        if len(mutable) < 13:
            source = Path(kwargs["source"])
            output = Path(kwargs["output"])
            start = float(kwargs["start"])
            end = float(kwargs["end"])
            focus_x = float(kwargs.get("focus_x", 50))
            zoomed = await _prepare_zoomed_clip(source, output, start, end, zoom, focus_x)
            try:
                forwarded = {**kwargs, "source": zoomed, "start": 0.0, "end": end - start, "focus_x": 50.0}
                await render_short(**forwarded)
            finally:
                zoomed.unlink(missing_ok=True)
            return

        source = Path(mutable[0])
        output = Path(mutable[1])
        start = float(mutable[2])
        end = float(mutable[3])
        focus_x = float(mutable[12])
        zoomed = await _prepare_zoomed_clip(source, output, start, end, zoom, focus_x)
        try:
            mutable[0] = zoomed
            mutable[2] = 0.0
            mutable[3] = end - start
            mutable[12] = 50.0
            await render_short(*mutable, **kwargs)
        finally:
            zoomed.unlink(missing_ok=True)

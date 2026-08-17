from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from app.core.config import get_settings
from .rendering import render_short


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


async def render_short_limited(*args: Any, **kwargs: Any) -> None:
    """Bound final Short rendering through the shared FFmpeg encode gate."""
    async with media_encode_slot():
        await render_short(*args, **kwargs)

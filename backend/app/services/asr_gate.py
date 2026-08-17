import asyncio
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from app.core.config import get_settings


@dataclass(frozen=True)
class ASRTicket:
    id: str
    resource_key: str


class ASRQueueGate:
    """FIFO concurrency gate for memory-heavy ASR work.

    A plain ``asyncio.Semaphore`` protects capacity, but it does not expose who
    is waiting. ClipKaro needs both: strict process-wide concurrency control and
    queue metadata that can be surfaced over the existing job/SSE channel.

    The production API intentionally runs one Uvicorn worker, so this
    process-wide gate is global for the deployed API container. If the API is
    ever scaled to multiple worker processes/containers, replace this with a
    distributed queue/semaphore (for example Redis) before increasing workers.
    """

    def __init__(self, concurrency: int) -> None:
        self.limit = max(1, int(concurrency))
        self._condition = asyncio.Condition()
        self._waiting: deque[ASRTicket] = deque()
        self._active: dict[str, ASRTicket] = {}

    @staticmethod
    def resource_key(resource: str | Path) -> str:
        return str(Path(resource).expanduser().resolve(strict=False))

    async def acquire(self, resource: str | Path) -> ASRTicket:
        ticket = ASRTicket(str(uuid.uuid4()), self.resource_key(resource))
        async with self._condition:
            self._waiting.append(ticket)
            try:
                while True:
                    is_head = bool(self._waiting) and self._waiting[0].id == ticket.id
                    if is_head and len(self._active) < self.limit:
                        self._waiting.popleft()
                        self._active[ticket.id] = ticket
                        # When concurrency > 1, another queued ticket may now be
                        # eligible immediately. Wake it without waiting for a
                        # release from this ticket.
                        self._condition.notify_all()
                        return ticket
                    await self._condition.wait()
            except BaseException:
                # Cancellation while queued must never leave a ghost ticket
                # that permanently blocks every item behind it.
                self._waiting = deque(item for item in self._waiting if item.id != ticket.id)
                self._condition.notify_all()
                raise

    async def release(self, ticket: ASRTicket) -> None:
        async with self._condition:
            self._active.pop(ticket.id, None)
            self._condition.notify_all()

    @asynccontextmanager
    async def slot(self, resource: str | Path) -> AsyncIterator[None]:
        ticket = await self.acquire(resource)
        try:
            yield
        finally:
            await self.release(ticket)

    def snapshot(self, resource: str | Path) -> dict | None:
        """Return exact queue state for a video's ASR request.

        ``queue_position`` is 1-based for waiting jobs and 0 for a request that
        is currently consuming an ASR slot.
        """
        key = self.resource_key(resource)
        if any(ticket.resource_key == key for ticket in self._active.values()):
            return {
                "asr_state": "running",
                "queue_position": 0,
                "queue_size": len(self._waiting),
                "asr_active": len(self._active),
                "asr_limit": self.limit,
            }
        for position, ticket in enumerate(self._waiting, start=1):
            if ticket.resource_key == key:
                return {
                    "asr_state": "queued",
                    "queue_position": position,
                    "queue_size": len(self._waiting),
                    "asr_active": len(self._active),
                    "asr_limit": self.limit,
                }
        return None

    def overview(self) -> dict:
        return {
            "queue_size": len(self._waiting),
            "asr_active": len(self._active),
            "asr_limit": self.limit,
        }


_gate: ASRQueueGate | None = None
_gate_loop: asyncio.AbstractEventLoop | None = None


def _get_gate() -> ASRQueueGate:
    """Create one gate per running event loop.

    FastAPI production uses one long-lived loop. Recreating the gate when a
    different loop appears keeps isolated TestClient/pytest event loops from
    inheriting asyncio primitives bound to an old loop.
    """
    global _gate, _gate_loop
    loop = asyncio.get_running_loop()
    configured_limit = max(1, int(get_settings().asr_concurrency))
    if _gate is None or _gate_loop is not loop:
        _gate = ASRQueueGate(configured_limit)
        _gate_loop = loop
    elif _gate.limit != configured_limit and not _gate.overview()["queue_size"] and not _gate.overview()["asr_active"]:
        _gate = ASRQueueGate(configured_limit)
    return _gate


@asynccontextmanager
async def asr_slot(resource: str | Path) -> AsyncIterator[None]:
    gate = _get_gate()
    async with gate.slot(resource):
        yield


def asr_queue_snapshot(resource: str | Path) -> dict | None:
    if _gate is None:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    if _gate_loop is not loop:
        return None
    return _gate.snapshot(resource)


def asr_queue_overview() -> dict:
    if _gate is None:
        return {"queue_size": 0, "asr_active": 0, "asr_limit": max(1, int(get_settings().asr_concurrency))}
    return _gate.overview()

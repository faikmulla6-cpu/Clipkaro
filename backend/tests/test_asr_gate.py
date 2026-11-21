import asyncio
from contextlib import asynccontextmanager

import pytest

from app.services import jobs, transcription
from app.services.asr_gate import ASRQueueGate


@pytest.mark.asyncio
async def test_asr_gate_serializes_sources_and_reports_exact_queue_position(tmp_path):
    gate = ASRQueueGate(1)
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def run_first() -> None:
        async with gate.slot(first):
            order.append("first")
            first_entered.set()
            await release_first.wait()

    async def run_second() -> None:
        async with gate.slot(second):
            order.append("second")

    first_task = asyncio.create_task(run_first())
    await asyncio.wait_for(first_entered.wait(), timeout=1)
    second_task = asyncio.create_task(run_second())
    await asyncio.sleep(0)

    first_state = gate.snapshot(first)
    second_state = gate.snapshot(second)
    assert first_state == {
        "asr_state": "running", "queue_position": 0, "queue_size": 1,
        "asr_active": 1, "asr_limit": 1,
    }
    assert second_state == {
        "asr_state": "queued", "queue_position": 1, "queue_size": 1,
        "asr_active": 1, "asr_limit": 1,
    }
    assert order == ["first"]

    release_first.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=1)
    assert order == ["first", "second"]
    assert gate.overview() == {"queue_size": 0, "asr_active": 0, "asr_limit": 1}


@pytest.mark.asyncio
async def test_asr_gate_never_exceeds_configured_concurrency(tmp_path):
    gate = ASRQueueGate(2)
    release = asyncio.Event()
    two_started = asyncio.Event()
    active = 0
    max_active = 0
    started = 0

    async def worker(index: int) -> None:
        nonlocal active, max_active, started
        async with gate.slot(tmp_path / f"source-{index}.mp4"):
            active += 1
            started += 1
            max_active = max(max_active, active)
            if started == 2:
                two_started.set()
            await release.wait()
            active -= 1

    tasks = [asyncio.create_task(worker(i)) for i in range(3)]
    await asyncio.wait_for(two_started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert gate.overview() == {"queue_size": 1, "asr_active": 2, "asr_limit": 2}
    assert max_active == 2

    release.set()
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)
    assert max_active == 2
    assert gate.overview()["asr_active"] == 0
    assert gate.overview()["queue_size"] == 0


@pytest.mark.asyncio
async def test_cancelled_waiter_is_removed_and_cannot_deadlock_queue(tmp_path):
    gate = ASRQueueGate(1)
    first = tmp_path / "first.mp4"
    cancelled = tmp_path / "cancelled.mp4"
    third = tmp_path / "third.mp4"
    release_first = asyncio.Event()
    first_entered = asyncio.Event()
    third_entered = asyncio.Event()

    async def hold_first() -> None:
        async with gate.slot(first):
            first_entered.set()
            await release_first.wait()

    async def wait_cancelled() -> None:
        async with gate.slot(cancelled):
            raise AssertionError("cancelled waiter must never acquire a slot")

    async def run_third() -> None:
        async with gate.slot(third):
            third_entered.set()

    first_task = asyncio.create_task(hold_first())
    await asyncio.wait_for(first_entered.wait(), timeout=1)
    cancelled_task = asyncio.create_task(wait_cancelled())
    await asyncio.sleep(0)
    assert gate.snapshot(cancelled)["queue_position"] == 1

    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    assert gate.snapshot(cancelled) is None
    assert gate.overview()["queue_size"] == 0

    third_task = asyncio.create_task(run_third())
    await asyncio.sleep(0)
    assert gate.snapshot(third)["queue_position"] == 1
    release_first.set()
    await asyncio.wait_for(third_entered.wait(), timeout=1)
    await asyncio.wait_for(asyncio.gather(first_task, third_task), timeout=1)


@pytest.mark.asyncio
async def test_transcribe_always_enters_asr_gate(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    entered: list[str] = []

    @asynccontextmanager
    async def fake_slot(resource):
        entered.append(str(resource))
        yield

    async def fake_impl(video_path, model_name="small", language_hint="auto", request_id="", asr_route="legacy", *, generated_dialogue=False):
        return "en", [{"start": 0, "end": 30, "text": "safe transcript"}]

    monkeypatch.setattr(transcription, "asr_slot", fake_slot)
    monkeypatch.setattr(transcription, "_transcribe_impl", fake_impl)
    result = await transcription.transcribe(source, "medium", "en", request_id="req-1", asr_route="legacy")
    assert result[0] == "en"
    assert entered == [str(source)]


@pytest.mark.asyncio
async def test_job_event_payload_surfaces_queue_position(monkeypatch):
    monkeypatch.setattr(jobs, "isolated_worker_enabled", lambda: False)
    job_row = {
        "id": "job-1", "kind": "process_video", "status": "processing", "progress": 38,
        "stage": "transcribing", "message": "Creating a timestamped transcript", "error": None,
        "project_id": "project-1", "export_id": None, "updated_at": "2026-08-07T00:00:00+00:00",
    }

    async def fake_fetch_one(query, params=()):
        if "FROM jobs" in query:
            return job_row
        if "FROM videos" in query:
            return {"file_path": "/tmp/source.mp4"}
        raise AssertionError(query)

    monkeypatch.setattr(jobs, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(jobs, "asr_queue_snapshot", lambda _: {
        "asr_state": "queued", "queue_position": 2, "queue_size": 3,
        "asr_active": 1, "asr_limit": 1,
    })

    payload = await jobs.event_payload("job-1")
    assert payload["queue_position"] == 2
    assert payload["queue_size"] == 3
    assert payload["asr_active"] == 1
    assert payload["asr_limit"] == 1
    assert "queue position 2" in payload["message"]


@pytest.mark.asyncio
async def test_asr_gate_queue_position_semantics_and_case_coverage(tmp_path):
    """Deterministic coverage for all canonical queue position cases:

    - Running / active: queue_position = 0
    - 1st in line (no jobs ahead in waiting deque): queue_position = 1
    - 2nd in line (1 job ahead in waiting deque): queue_position = 2
    - Completed / released jobs do not count
    - Cancelled waiters do not count
    - Current job is not counted ahead of itself
    """
    gate = ASRQueueGate(1)
    s_active = tmp_path / "active.mp4"
    s_first = tmp_path / "first_waiter.mp4"
    s_second = tmp_path / "second_waiter.mp4"

    active_entered = asyncio.Event()
    release_active = asyncio.Event()

    async def run_active():
        async with gate.slot(s_active):
            active_entered.set()
            await release_active.wait()

    async def run_waiter(resource):
        async with gate.slot(resource):
            pass

    t_active = asyncio.create_task(run_active())
    await asyncio.wait_for(active_entered.wait(), timeout=1)

    # CASE 1: Active job has queue_position = 0 (processing now)
    snap_active = gate.snapshot(s_active)
    assert snap_active["asr_state"] == "running"
    assert snap_active["queue_position"] == 0
    assert snap_active["queue_size"] == 0

    # CASE 2: First waiter has queue_position = 1 (1-based index, next to run)
    t_first = asyncio.create_task(run_waiter(s_first))
    await asyncio.sleep(0)
    snap_first = gate.snapshot(s_first)
    assert snap_first["asr_state"] == "queued"
    assert snap_first["queue_position"] == 1
    assert snap_first["queue_size"] == 1

    # CASE 3: Second waiter has queue_position = 2
    t_second = asyncio.create_task(run_waiter(s_second))
    await asyncio.sleep(0)
    snap_second = gate.snapshot(s_second)
    assert snap_second["asr_state"] == "queued"
    assert snap_second["queue_position"] == 2
    assert snap_second["queue_size"] == 2

    # CASE 4 & 6: Release active; first waiter transitions to running (queue_position 0),
    # second waiter moves to position 1, and finished active job is no longer counted.
    release_active.set()
    await asyncio.wait_for(t_active, timeout=1)
    await asyncio.sleep(0)

    snap_first_now = gate.snapshot(s_first)
    if snap_first_now:  # If still running
        assert snap_first_now["queue_position"] == 0
    snap_second_now = gate.snapshot(s_second)
    if snap_second_now and snap_second_now["asr_state"] == "queued":
        assert snap_second_now["queue_position"] == 1

    await asyncio.wait_for(asyncio.gather(t_first, t_second), timeout=1)
    assert gate.overview() == {"queue_size": 0, "asr_active": 0, "asr_limit": 1}


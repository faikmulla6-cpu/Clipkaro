# Atomic usage reservation lifecycle

ClipKaro treats quota as a durable reservation, not as a read-then-increment counter.

## Karo Minutes

1. FFprobe determines source duration.
2. When the video transitions to `validated`, a SQLite trigger reserves the complete source duration in the active entitlement period in the same write transaction.
3. The reservation immediately counts against `source_minutes`, so another simultaneous upload cannot spend the same remaining minutes.
4. When the project becomes `ready`, the reservation becomes `finalized` without a second usage increment.
5. If processing fails or the project is deleted before success, only a still-`reserved` reservation is refunded and marked `released`.
6. Reprocessing an already-finalized project does not charge the source a second time.

## Short exports

1. Inserting a queued export atomically reserves one export slot.
2. The reserved slot immediately counts in `exports_used`, so a competing render cannot claim the same last slot.
3. A `ready` export finalizes the reservation with no second increment.
4. A failed or deleted export refunds a still-reserved slot exactly once.

## Concurrency and restart guarantees

- SQLite serializes the reservation write and quota check in one transaction.
- `busy_timeout=10000` lets short writer contention wait instead of failing immediately with `database is locked`.
- Reservations survive process/VPS restarts because they live in SQLite.
- Interrupted processing jobs resume and reuse their reservation.
- Interrupted exports are marked failed and therefore refund a still-reserved slot.
- If an export was already committed as `ready` before a restart, recovery marks its job completed rather than hiding a finalized paid export.

## Invariants

- `reserved` quota is unavailable to other requests.
- `finalized` quota is consumed and is never refunded by retry/deletion.
- `released` quota has been refunded and cannot be refunded again.
- Legacy post-success route increments are intentionally suppressed because reservation time is now the single accounting write.

The regression suite contains simultaneous two-request races for both Karo Minutes and exports to prove that only one request can acquire the final available quota.

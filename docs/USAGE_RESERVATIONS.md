# Atomic usage reservation lifecycle

ClipKaro treats creation quota as a durable reservation, not as a read-then-increment counter.

## Karo Minutes and AI Short creation credits

1. FFprobe determines source duration.
2. When a new source video transitions to `validated`, the database atomically reserves both its source-processing minutes and one AI Short creation credit for the active entitlement period.
3. The creation credit is represented by the active/finalized `minutes` reservation for that source project, so concurrent sources cannot spend the same last Short credit.
4. The complete source duration immediately counts against `source_minutes`.
5. When the project becomes `ready`, the reservation becomes `finalized` without a second usage increment.
6. If processing fails before success, only a still-`reserved` reservation is refunded and marked `released`.
7. Reprocessing an already-finalized project does not consume another AI Short creation credit or process those source minutes a second time.

## Exports and re-exports

1. Paid plans do not consume AI Short creation credits when an already-created Short is rendered or rendered again.
2. Paid export rows therefore create no `kind='export'` quota reservation.
3. Changing captions, framing, trim/order, style, resolution or another render setting does not consume another paid creation credit.
4. Free retains its small export allowance to bound unpaid FFmpeg compute.
5. Free export inserts reserve that allowance atomically; a successful render finalizes it and a failed/deleted render refunds a still-reserved Free export slot exactly once.

## Concurrency and restart guarantees

- SQLite and PostgreSQL serialize the source reservation check with the usage write.
- `busy_timeout=10000` lets short SQLite writer contention wait instead of failing immediately with `database is locked`.
- Reservations survive process/VPS restarts because they live in the database.
- Interrupted processing jobs resume and reuse their reservation.
- Interrupted paid exports are marked failed without affecting creation credits.
- Interrupted Free exports refund any still-reserved Free export slot.
- If an export was already committed as `ready` before a restart, recovery marks its job completed rather than hiding a finished export.

## Invariants

- `reserved` creation/minute quota is unavailable to another new-source request.
- `finalized` creation/minute quota remains consumed and is not charged again by retry.
- `released` quota has been refunded and cannot be refunded again.
- Paid export and re-export actions never decrement `shorts_remaining`.
- Free export allowance remains independent of AI Short creation capacity.
- Legacy post-success usage increments are suppressed because reservation time is the single accounting write.

The regression suite covers concurrent source reservations, creation-credit exhaustion, Free export reservations, and paid unlimited re-exports.

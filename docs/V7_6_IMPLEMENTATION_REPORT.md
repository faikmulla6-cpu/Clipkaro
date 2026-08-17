# ClipKaro AI v7.6 — Accuracy and Runtime Reanalysis

## Outcome

This release removes a misleading timing claim and introduces an explicit two-tier
alignment contract. Native Whisper word timestamps are now identified as
`native_stabilized`; only WhisperX acoustic alignment is identified as
`forced_aligned`. Production can set `REQUIRE_FORCED_ALIGNMENT=true`, which blocks
exports unless verified forced alignment exists.

## Implemented

- Optional WhisperX forced-alignment worker profile with fail-closed quality checks.
- Independent ASR consensus and forced-alignment gates remain part of pipeline provenance.
- Roman Hinglish stays a display transformation; ASR verification remains in native script.
- Source burned-caption band is stored, returned by the API, and represented in Studio.
- Studio uses the same effective caption-position rule as export and exposes Above placement.
- FFmpeg renders are concurrency-bounded for memory-limited Windows systems.
- Version reporting is unified at 7.6.0; stale 5.0.1 health metadata is removed.
- CSRF token comparison is constant-time and CORS methods/headers are restricted.

## Production profile

Current Hostinger production uses the dedicated backend `worker` Docker target, which installs the pinned `backend/requirements-alignment.txt` automatically. Configure:

```env
APP_ENV=production
ALIGNMENT_BACKEND=whisperx
REQUIRE_FORCED_ALIGNMENT=true
REQUIRE_ASR_CONSENSUS=true
SEED_DEMO_USER=false
```

The local/laptop profile intentionally keeps `ALIGNMENT_BACKEND=native` and `REQUIRE_FORCED_ALIGNMENT=false` unless explicitly opted in. Production is fail-closed on WhisperX; Hindi/Hinglish and Marathi alignment models are pinned to immutable revisions in `backend/app/services/forced_alignment.py`.

## Verification

- Backend tests: 41 passed.
- Python compile check: passed.
- Frontend clean-install/build: blocked by corrupted npm registry tarballs in the build
  environment. This is an environment/dependency-fetch failure, not recorded as a pass.

## Remaining scale boundary

FastAPI background tasks and SQLite are suitable only for a single-node creator preview.
Before multi-replica public launch, move jobs to Redis plus a durable worker and migrate
the relational store to PostgreSQL. This release does not disguise that limitation.

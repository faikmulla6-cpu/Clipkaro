# ClipKaro AI v7.3 — Verified Pipeline Migration

## Release outcome

v7.3 prevents projects created by older transcription pipelines from silently producing inaccurate or duplicate-caption exports. Legacy projects are automatically rebuilt, and export is allowed only after transcript provenance, model agreement, and word alignment pass.

## Production changes

- Every transcript segment is stamped with a pipeline version, component fingerprint, and origin.
- Project reads detect legacy data, hide stale clips, queue reprocessing, and expose live upgrade progress.
- Export has a second independent safety gate and returns HTTP 409 while automatic rebuilding is underway.
- ASR transcripts require small/turbo agreement and stabilized word timing; manual transcripts remain explicitly identified.
- Roman-Hinglish display text is preserved through export comparison and caption timing.
- Burned-in subtitle OCR runs again immediately before render, preventing stale detection results.
- Existing lower-third captions move generated captions to a safe upper position.

## Validation

- Backend: 38 tests passed.
- Python compile validation passed for application and tests.
- Both supplied failed exports were correctly detected as containing persistent lower-third text (confidence 0.500 and 0.667).
- Frontend dependency download could not be repeated in the isolated build environment because its npm registry proxy returned corrupted tarballs. The production build must be rerun in the Windows release environment before deployment.

## Deployment behavior

The first visit to a legacy project starts a one-time re-analysis. Users see a dedicated upgrade screen instead of old clips. After the job reaches `ready`, only newly generated v7.3 clips are displayed. Attempting to export an old clip directly also starts the upgrade and blocks that export.

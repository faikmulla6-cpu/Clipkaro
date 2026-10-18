# Clipkaro Smart Layout v2 — isolated engineering and release gate

**Status: development branch / DRAFT PULL REQUEST ONLY. NOT DEPLOYED.**
Base: `feature/creator-pulse-next-move`. Branch: `work/secure-smart-layout-v2-20261018`.

## Problem and intended result

The old editor plays two copies of one source video with fixed left/right CSS
positions; these are not face detections. The v1 export separately detects
camera scenes, so its framing is unrelated to the editor guide. That explains
the same speaker appearing twice in the user's screenshots.

V2 analyzes the private source once, derives all requested modes from the
same verified shot evidence, and uses a canonical timeline of source pixel
crops in both a Canvas 2D browser preview and the final FFmpeg graph. For
single-face/uncertain shots, never fabricate a second person.

## Implemented on this branch

- `backend/app/services/smart_layout_contract.py`: versioned strict
  schema for clip-relative scenes, finite coordinates, 24-scene cap, and
  actual one-/two-face crop rectangles; malicious plans fail closed.
- `backend/app/services/smart_layout_variants.py`: Auto Director, Dual Stack
  and Speaker Focus from one authorized scene analysis. Speaker turns only
  affect focus shots. No duplicate-person split.
- `backend/app/services/smart_layout_cache.py`: owner/project scoped B2 key
  containing SHA-256 fingerprint of video, exact generation, clip start/end
  and model version. Key holds no public or signed access token.
- `backend/app/services/smart_layout_job.py`: bounded, no-export-charge,
  private Modal media worker. Rechecks ownership and source expiry before
  saving the result. A failed analysis cannot mark the project/export failed.
- `backend/app/api/smart_layout_v2.py`: authenticated, default-disabled
  analysis GET/POST endpoints, source authorization, global/user compute
  budgets, idempotent job checks and strict cache validation. Private MP4
  media is streamed by Clipkaro itself in bounded HTTP ranges, rather than
  redirecting a Canvas decoder to another B2 origin.
- `frontend/lib/smart-layout-timeline.ts`: no network dependencies;
  draws the actual analyzed crop at the source timestamp from ONE authorized
  <video> into Canvas. V2 editor displays analysis pending/error/retry instead
  of pretending a fixed two-panel CSS guide has tracked a face.
- `backend/app/services/smart_layout_render_v2.py`: scene-local FFmpeg
  crop graph consuming the exact private JSON plan, at 720x1280 or 1080x1920,
  with original audio preserved.
- `backend/app/services/smart_layout_captions.py`: splits ASS Dialogue
  events at actual camera cuts, places captions on the seam only for genuine
  Dual Stack segments and maps scene times through Smart Edit's retained
  source ranges. Other scenes preserve the chosen caption settings.
- Clip-level layout selection persisted in existing Smart Edit plan JSON.
  Unknown modes are rejected; no new database table or migration required.
- `backend/app/services/smart_layout_cleanup.py`: strict project-scoped
  versioned-cache purge helper (not yet attached to source deletion or expiry
  pending a dedicated live B2 permissions audit).

## Security and compatibility

- Both flags must be enabled together for a canary ONLY:
  `KARO_REAL_PREVIEW_ENABLED=true` on the backend and
  `NEXT_PUBLIC_SMART_LAYOUT_V2=true` at frontend BUILD TIME.
  Both default to off. Do not enable in production before release gates.
- Input is a clip ID only, matched via the project's authenticated user.
  The client never supplies an object key, signed URL or crop plan to FFmpeg.
- Source-generation mismatch, expiry, superseded clip, invalid face count,
  NaN/infinite coordinates, timeline gaps and cache corruption fail closed.
- No third-party face API, no new secret, no public bucket, no new B2 CORS.
- A pre-export readiness check runs before inserting a billable export row.
  A queued v2 render is bound to the currently authorized cached plan.
- The old Creator Pulse behavior is preserved unless both feature flags are
  intentionally enabled.
- Global job queue definitions, imported OpenShorts code and imported
  OmniVoice/GenVoice code are untouched.

## Tests performed (2026-10-18)

- Python contract, media and security tests in isolated Modal: 25 passed
  before the subsequent persistence/cache-purge test additions.
- Existing rendering, Smart Edit, layout, billing, subscription and
  source-availability regression suite in isolated Modal: 156 passed.
- Node geometry and Canvas tests passed.
- Next.js production build with v2 enabled compiled and typechecked.
- Actual 59.56-second private podcast: detected 1 wide + 3 single-person
  shots, and rendered valid full-length 360x640 MP4s for requested Dual Stack
  and Speaker Focus without creating exports or uploading output.
  Correct behavior for that source is a single subject, NOT two fake panels.

## Release blockers — do not merge or deploy until all are cleared

1. Rerun the expanded test suite and obtain passing GitHub CI on the FINAL
   commit (including persisted preferences and mock B2 purge tests).
2. Review/complete the new-cache deletion hooks in both project deletion
   and source-expiry cleanup. Audit B2 ListObjectVersions permissions and
   secure expiry of older object generations; the helper alone is insufficient.
3. Verify actual authenticated browser playback through the production
   Next/Hostinger proxy (cookies, credentialed CORS, CSP and Range seek).
   Do not broaden B2 public ACL or global bucket CORS as a workaround.
4. Confirm preview/export pixel parity for dual-person footage, two-way
   speaking transitions, camera cuts, profile faces and Smart Edit reorder.
5. Before any production enabling, canary a small approved group, monitor
   analysis job queue/worker cost, handle rollback and compare the final
   downloaded MP4 with the browser preview.
6. Improve face tracking robustness for difficult angles if testing reveals
   misses. The present model remains Clipkaro's OpenCV CPU detector;
   it is NOT a licensed new MediaPipe or voice-identity model.
7. Get explicit rollout approval after the full MP4/caption review.

No live customer project, database, billing row or Backblaze bucket setting
was changed by this development work.

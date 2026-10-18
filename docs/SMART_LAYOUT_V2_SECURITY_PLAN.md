# Clipkaro Smart Layout v2 — security-first integration (work in progress)

## Status and scope

This is **isolated, unmerged development work**. It does not replace the
currently deployed editor, modify OpenShorts/OmniVoice, change B2 CORS, use an
external AI API, create paid exports, or change billing/entitlements.

The current editor draws two synchronized copies of the same browser video
using fixed 16%/84% horizontal positions. This **cannot** know whether one or
two faces are visible, and explains the duplicate-person screenshots. The
current Modal exporter instead runs an internal OpenCV scene analyzer. The
preview and export must share the **same authoritative timeline**.

## Shared contract (initial implementation)

- `backend/app/services/smart_layout_contract.py`: bounded serialization of
  already-analyzed scenes and exact source-pixel crop rectangles.
- `frontend/lib/smart-layout-timeline.ts`: untrusted JSON validation,
  scene lookup, focus easing and Canvas 2D painting using those rectangles.
- Python and Node contract tests cover duplicate people, scene gaps, malformed
  coordinates, caption positioning, camera cut changes and focus transitions.
- Timeline times are **clip-local**, with `source_start` explicitly encoded to
  avoid off-by-one-clip seek errors.
- All plans are limited to 180 seconds, 24 scenes, 42 speaker transitions per
  scene, finite numbers and dimensions <= 16384. No user IDs, signed URLs,
  face embeddings, cloud object keys or customer metadata belong in a plan.

Neither new module accesses storage or customer accounts. A plan is only a
description of authorized geometry; it does not authorize media access.

## Planned source-of-truth integration (NOT YET IMPLEMENTED)

1. **Ownership / gating**: only the authenticated clip owner can request a
   layout analysis. Verify clip -> video -> project -> user ownership. Never
   accept a client-supplied storage key, URL or user ID.
2. **Asynchronous worker**: launch ONE bounded, idempotent media-analysis job
   in the existing Modal worker; no FFmpeg or face model in the API container.
   Bind it to clip ID, source object generation, start/end, model version and
   optional edit-plan version. Limit concurrent jobs and retries per user.
   A preview analysis must not reserve or charge an AI Short or export.
3. **Private cache**: store a small, versioned JSON plan beneath the owner's
   existing B2 namespace, keyed by an irreversible hash of the source version
   and clip time range. Never include a signed URL in JSON or log it.
4. **Mode derivation**: analyze faces/scenes once, derive Auto Director,
   Dual Stack or Speaker Focus from the same evidence. Dual Stack needs two
   **co-visible** genuine faces, not two face detections from different
   moments. Otherwise show one speaker or a full-frame safe composition.
5. **Preview**: the editor fetches only its owner's cached plan, validates its
   schema, and paints frames from ONE authorized video source using the exact
   crop boxes. Playback, seek, trim, reordering and captions must resolve to
   the same source timestamp. If a plan is pending, clearly show "Analyzing"
   rather than a fake split. On failure, show an accurate retry state.
6. **Transport / CORS**: production `/projects/{id}/media` redirects to a
   time-limited B2 URL. Before enabling Canvas in production, verify an
   origin-restricted policy or implement an authenticated, bounded
   same-origin preview stream with correct HTTP Range support. Do **not**
   change bucket access from private to public, use wildcard credentials,
   embed long-lived presigned URLs, or loosen Clipkaro CSP to make it work.
7. **Final export**: consume the **same validated, versioned plan** that the
   editor paints; if source/clip/version has changed, invalidate/re-analyze.
   Do not recompute independent unshared face centers. Apply scene-specific
   caption placement (middle only for real dual shots). Exports are still
   created through the existing permission/quota path.
8. **Saved edits**: explicitly persist the selected layout and any permitted
   overrides in the existing clip-edit workflow. Reopen must show the chosen
   mode rather than revert to Classic.

## Hard security and product requirements

- No changes in `openshorts-main/` or `GENVOICE-V.2.0/`.
- Never authorize via a raw B2 key or a client-side plan alone.
- No use of third-party face/cloud AI without reviewing model, license and
  consent; no production bucket CORS updates without a dedicated audit.
- Bound worker CPU/time, payload size, DB job volume and storage operations.
- Return no user-identifying or sensitive speaker geometry beyond the owner's
  authorized source; no face embeddings, identities or emotion claims.
- Deletion and source expiry invalidate analysis objects.
- A Canvas SecurityError must **not** turn into a fake working layout.
- Use a feature flag/canary on new paths; preserve the existing production
  export until a full integration test passes.
- Visually compare scene crops, safe areas, subtitles, watermark, audio sync
  and 720p/1080p exports on **actual mixed-camera podcasts**.

## Release gate

1. Python contract and security tests pass.
2. Node geometry / Canvas tests pass.
3. Existing billing, account security, upload, source-access and render tests
   still pass.
4. Authenticated preview transport passes CORS and byte-range tests.
5. Same private source produces matching preview and export at camera cuts,
   across two-person scenes, solo shots and no-face fallbacks.
6. Production build passes, B2 stays private, and no other repo tree differs.
7. Human approval of screenshots and a full MP4 before rollout.

**Do not merge or deploy this branch until these gates pass.**

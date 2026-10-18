# Smart Layout v2 — secure implementation and staged rollout

**Branch:** `work/secure-smart-layout-v2-20261018`. The imported OpenShorts and
OmniVoice source trees remain untouched. No production user media was modified
during development.

## Why the earlier editor was wrong

The old editor painted two fixed-position copies of one video. It could not
know whether two speakers appeared together. V2 replaces that illusion with a
shared, authenticated shot-by-shot source-pixel plan. It uses a single video
decoder and Canvas 2D for the preview, and the exact same validated crop
coordinates in FFmpeg for export. Missing faces become safe single-speaker
or full-source compositions; speakers are not duplicated to fill a split.

## Implementation

- `smart_layout_contract.py`, `smart_layout_variants.py` and
  `smart_layout_render_v2.py`: bounded, validated crop/source timeline,
  mode derivation, and true per-scene video composition.
- `smart_layout_job.py`: isolated analysis worker with a generation-locked
  B2 source download; checks owner, expiry, source generation and clip range.
- `smart_layout_repository.py`: private, TTL-limited PostgreSQL JSON cache
  with owner/project/clip keys, source-generation fingerprint and **foreign
  keys that cascade on project/clip deletion**. The retention sweep deletes
  expired records. There are **no B2 cache objects and no B2 version purge**.
- `smart_layout_v2.py`: authenticated per-account capability discovery,
  opt-in canary authorization, idempotent capped analysis jobs, strict cache
  validation and same-origin private MP4 byte-range streaming.
- `frontend/lib/smart-layout-timeline.ts` and the editor: one source video,
  real crop-based Canvas preview, pending/error/retry, no fake duplicate
  speaker preview. The editor discovers capability at runtime, so Hostinger
  **does not need a NEXT_PUBLIC flag** for this feature.
- `smart_layout_captions.py` and Smart Edit integration: actual scene-wise
  caption regions and saved layout preferences.
- `jobs.py`: isolated FIFO media workers can claim/recover preview analysis
  jobs, while paid export/process jobs take priority.
- B2 source remains private, and source bytes are pinned to the confirmed
  VersionId or ETag during both preview and analysis. No bucket-wide CORS
  changes, face embeddings, third-party speaker-ID APIs, or raw keys in JSON.

## Controlled enabling

Backend defaults to OFF. A canary is enabled only with BOTH variables on the
Modal backend:

`KARO_REAL_PREVIEW_ENABLED=true`
`KARO_REAL_PREVIEW_CANARY_USERS=<explicit authorized user UUID>`

With no UUID allowlist, nobody is enabled; `*` is deliberately required for
an all-user rollout. The frontend queries `/api/v1/smart-layout-v2/capabilities`
using the existing signed-in cookie. Unavailable endpoints show an explicit
honest status instead of the old fake preview.

The PostgreSQL cache table is created only when the feature is explicitly
enabled at application startup. Creating it does not change existing rows or
billing. New rows expire no later than the source and at most 14 days after
analysis. A project deletion cascades to its analysis rows automatically.

## Quality assurance and release gates

- Private read-only real source QA: a 59.56-second podcast successfully
  rendered complete Dual Stack and Speaker Focus videos with 1 wide and 3
  single-speaker shots. No export charge was created.
- Isolated Modal regression suite (prior B2 cache design): **167 tests
  passed**, plus frontend production build and TS checks. Re-run after the
  PostgreSQL cache migration; don't rely on old results for this change.
- Required before enabling live users: successful PostgreSQL FK/TTL test,
  isolated billing/render/security tests, GitHub CI on final commit, then
  authenticated Hostinger browser seek/frame/CORS verification using a canary.
- Verify actual side-by-side camera scenes, speaker switching and caption
  alignment before disabling the flag for all customers.
- Do not merge/deploy blindly or edit public Backblaze settings, external code,
  or payment/usage data as part of this release.

### Important storage finding

Production B2 credentials returned `NotImplemented` for S3
`ListObjectVersions` and HTTP 401 for the B2 Native authorization probe.
Therefore relying on S3 version enumeration would have been incorrect.
The new design stores **only source videos in B2**, and face crop geometry in
owner-scoped PostgreSQL rows that can be removed by ordinary database FK
cascade and a TTL sweep.

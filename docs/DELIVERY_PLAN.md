# Delivery plan

This is structured so it can be copied into Linear as one project with six milestones. Priorities use P0 (launch blocker), P1 (important), and P2 (polish).

## Milestone 1 — Upload and video engine

| Issue | Priority | Estimate | Acceptance |
|---|---:|---:|---|
| CK-1 Secure upload endpoint | P0 | 3 | Streams supported files, rejects invalid type/size, removes partial failures |
| CK-2 Video metadata probe | P0 | 2 | Reads duration and rejects plan violations |
| CK-3 Manual timestamp export | P0 | 5 | FFmpeg produces downloadable MP4 from valid start/end |
| CK-4 Upload UI | P0 | 3 | Drag/drop, progress, errors, rights confirmation |

## Milestone 2 — Transcription

| Issue | Priority | Estimate | Acceptance |
|---|---:|---:|---|
| CK-5 Audio extraction | P0 | 2 | Generates 16 kHz mono WAV and cleans temporary file |
| CK-6 Whisper worker | P0 | 5 | Produces text segments with timestamps on CPU/int8 |
| CK-7 Transcript persistence | P0 | 3 | Saves language, full text, and segment JSON |
| CK-8 Progress state | P1 | 3 | Creator sees each processing stage and actionable failures |

## Milestone 3 — AI clip finder

| Issue | Priority | Estimate | Acceptance |
|---|---:|---:|---|
| CK-9 Candidate window builder | P0 | 3 | Generates useful 20–90 second windows |
| CK-10 Explainable ranking | P0 | 5 | Scores hooks, value, emotion, structure, and endings |
| CK-11 Candidate deduplication | P0 | 2 | Top results do not overlap |
| CK-12 Suggestions UI | P0 | 5 | Shows timestamp, hook, title, reason, score, and platform |

## Milestone 4 — Shorts renderer

| Issue | Priority | Estimate | Acceptance |
|---|---:|---:|---|
| CK-13 9:16 render preset | P0 | 5 | Produces 720×1280 H.264/AAC MP4 |
| CK-14 Burned captions | P0 | 5 | Captions are readable and stay within two mobile-safe lines |
| CK-15 Hook and watermark | P0 | 3 | Hook and plan-aware brand mark render reliably |
| CK-16 Export status/download | P0 | 3 | Job can be polled and final file downloaded |

## Milestone 5 — SaaS controls

| Issue | Priority | Estimate | Acceptance |
|---|---:|---:|---|
| CK-17 Authentication and ownership | P0 | 5 | Every media resource is scoped to the signed-in user |
| CK-18 Monthly usage ledger | P0 | 3 | Limits are atomic and reset by billing month |
| CK-19 Razorpay billing | P1 | 8 | Verified, idempotent webhooks activate correct plans |
| CK-20 File lifecycle cleanup | P0 | 3 | Expired uploads/exports are deleted automatically |

## Milestone 6 — Beta launch

| Issue | Priority | Estimate | Acceptance |
|---|---:|---:|---|
| CK-21 End-to-end test matrix | P0 | 5 | Covers short/long, portrait/landscape, silent, corrupt, and multilingual files |
| CK-22 Observability | P0 | 3 | Errors, render duration, queue wait, and failure rate are visible |
| CK-23 Hindi/Hinglish beta | P1 | 8 | Transcription and captions pass native-speaker QA |
| CK-24 Legal launch pack | P0 | 3 | Terms, privacy, rights attestation, expiry, and takedown flow are published |

## Launch metrics

- Upload-to-suggestion success ≥ 95%.
- Export success ≥ 97% for supported inputs.
- Median suggestion latency under 0.5× source duration on target worker.
- Suggestion-to-export conversion ≥ 25%.
- Seven-day creator return rate ≥ 20%.
- Compute and storage cost below 30% of realised subscription revenue.

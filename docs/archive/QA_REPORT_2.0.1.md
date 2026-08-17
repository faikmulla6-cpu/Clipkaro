# QA report — Launch Edition 2.0.1

> Historical archive. This document is preserved only as evidence for the old release and must not be used to certify the current product.

## 5.0.0 synchronization acceptance — 2026-07-11

- 13 backend tests passed, including millisecond word preservation and correction anchoring.
- Next.js production build and TypeScript validation passed.
- Production dependency audit reports zero vulnerabilities.
- Visual sampling at five word timestamps confirmed the active highlight advances on schedule.
- Full authenticated upload, processing, timed-caption API, export and download flow passed.
- Acceptance export: 43 seconds, 720×1280, H.264/AAC, 6,265,172 bytes.
- Source streaming returned HTTP 206 and an exact 1,024-byte range.

## Automated verification

- Frontend optimized production build: passed.
- TypeScript validation: passed.
- 15 application routes generated; dynamic creator/project routes compiled.
- Backend tests: 10 passed.
- Python dependency consistency: passed.
- Python bytecode compilation: passed.
- ZIP archive integrity: verified during packaging.

## Connected API coverage

- Anonymous requests cannot read authenticated resources.
- Signup creates a Free-plan account and signed session.
- Login returns the seeded launch account; logout removes session/CSRF cookies.
- Usage ledger initializes with the correct plan limit.
- Multipart upload persists an owned project, video, and job.
- Timestamped transcript analysis creates ranked clips and score breakdowns.
- Clip hook/title edits persist.
- Creator brand kit creation persists.
- 1080p/no-watermark Creator export queues with a job.
- A second account receives 404 for another user's project.
- A valid Razorpay signature activates the plan once; replay is idempotent.
- Missing FFmpeg returns a clear Windows PATH instruction instead of an empty failure.

## Media verification

A generated 1280×720 H.264/AAC source was rendered through the production renderer. The output was probed and visually inspected:

- 720×1280, 9:16
- 4.0 seconds
- H.264 video and AAC audio
- Hook text rendered
- Burned SRT captions rendered
- Custom wordmark and brand color rendered
- MP4 fast-start output completed

## Dependency advisory

The latest installed Next.js release currently resolves to a PostCSS version covered by a moderate advisory involving CSS stringify output. `npm audit` reports no upstream fix. ClipKaro does not accept or stringify user-supplied CSS, which materially limits reachability. Track the upstream advisory and upgrade immediately when a patched Next/PostCSS release is available.

## Items needing external launch credentials

- Razorpay API key, secret, monthly plan IDs, and webhook secret.
- HTTPS domain/reverse proxy.
- Production email provider for verification/reset (documented as hardening work).
- Object storage credentials when moving beyond a single-node launch.

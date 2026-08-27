# Changelog

## 7.8.0 Stage 2J finalization hardening

- Moved ordinary CI, critical product contracts and Fresh Launch certification onto GitHub-hosted Ubuntu runners while keeping heavyweight empirical QA on the self-hosted runner.
- Fixed the Fresh Launch repository-identity contract for `faikmulla6-cpu/Clipkaro` and added wrong-repository fail-closed coverage.
- Split Fresh Launch disk policy between ephemeral hosted image-build certification and heavyweight self-hosted qualification instead of applying the 25 GiB ASR floor to both.
- Fixed the FFmpeg/FFprobe missing-tool regression test to exercise the media-tool resolver rather than bypassing its production fallback.
- Upgraded Next.js to `16.3.3` and hardened PostCSS, Nanoid and Sharp lockfile floors to clear the production dependency-audit findings exposed by Ubuntu QA.
- Made Next generated route typing deterministic for production builds, removed tracked TypeScript compiler cache state, and added a build-hygiene release contract.
- Extended static release verification and CI/Fresh Launch enforcement so dependency, generated-file and frontend-build hygiene regressions fail closed.
- Consolidated every `/admin/*` API route under the dedicated Founder service-token router, removed legacy customer-role admin handlers, and mounted Founder Admin explicitly in the application bootstrap.
- Extended Founder Admin fail-closed defaults to the generic production template/legacy Compose path and hardened audit metadata redaction for token/secret key variants and credential-shaped values.
- Aligned API-backed media execution with the `media` image target so scanning, FFmpeg and rendering remain available while local WhisperX stays isolated in the heavyweight `worker` target.
- Fresh Launch now certifies that same `media` target instead of rebuilding the optional heavyweight WhisperX worker, reducing hosted-runner cost/time while preserving WhisperX qualification in the self-hosted ASR gate.

## 5.0.1 — Hindi Detection Fix

- Fixed colloquial Hindi being accepted as Urdu during automatic detection.
- Auto mode now retries Urdu as forced Hindi and compares uncertain English against Hindi.
- Hindi is the recommended default for this India-first product; explicit choices are never overridden.
- Added detected-language visibility and in-place language re-analysis without another upload or usage charge.
- Re-analysis regenerates transcript, ranked moments and caption timing from the retained source video.
- Added automated Hindi/Urdu disambiguation tests.

## 5.0.0 — Audio-Locked Captions

- Preserves faster-whisper word timestamps from audio through Studio and export.
- Uses accurate FFmpeg seeking and timed ASS events for per-word active highlighting.
- Maps transcript corrections back to original audio anchors instead of redistributing captions.
- Honors the spoken-language selection during transcription.
- Upgraded the 8 GB laptop default from `tiny` to the more accurate multilingual `base` model.
- Added beam-search decoding, tuned Silero VAD, word confidence and low-confidence indicators.
- Balances caption cards into two to four words and avoids orphan one-word cards.
- Uses relative ASS paths to prevent Windows drive-letter export failures.
- Validates output stream, size and duration before marking an export ready.
- Added timestamp integrity, active-word and correction-alignment regression tests.

## 2.0.1 — Processing diagnostics hotfix

- Fixed missing FFmpeg returning the wrong metadata type and immediately failing at 0%.
- Added an authenticated processing-engine preflight for FFmpeg, Whisper, storage, and active model.
- Added actionable pipeline errors with the exception type, failed stage, terminal logging, and preserved progress.
- Added a guaranteed diagnostic fallback in the upload screen instead of an empty red banner.
- Switched the local 8 GB laptop default to multilingual Whisper `tiny`.

## 2.0.0 — Launch Edition

- Replaced the static demo identity with signup/login/logout, Argon2 hashing, HttpOnly sessions, CSRF protection, ownership checks, and admin roles.
- Added durable job records and Server-Sent Event progress for video processing and export.
- Made upload, project lists/details, clip score breakdowns, Creator Studio, exports, analytics, templates, brand kits, calendar, account, and pricing data-connected.
- Added real 9:16, 4:5, and 1:1 FFmpeg rendering; five caption personalities; brand colors/wordmark; 720p/1080p plan controls.
- Added multilingual faster-whisper as a first-class dependency.
- Added Razorpay subscription creation, signed/idempotent webhooks, and plan activation.
- Added request rate limits, security headers, audit events, expiry cleanup, and cross-account isolation tests.
- Added Windows startup, launch, security, architecture, product strategy, and QA documentation.

## 1.0.0 — MVP

- Initial landing page, creator dashboard, upload, deterministic clip finder, FFmpeg renderer, usage limits, and Docker setup.
# v7.7.0

- Added a Hostinger VPS production stack with Caddy HTTPS, persistent volumes,
  health checks, same-origin API routing, and automatic restart policies.
- Reduced verified transcription cost by replacing the secondary turbo model
  with small and skipping secondary decode when consensus is disabled.
- Added bounded ASR CPU/worker settings and restart recovery for analysis jobs.
- Fixed backend Docker builds that expected a missing storage source directory.
- Added real FFmpeg health reporting and production deployment documentation.
# v7.8.0

- Learned from SamurAIGPT's open-source shorts pipeline and integrated its useful
  content profiling, density-aware duration, and score-first overlap concepts.
- Added Hindi, Roman-Hinglish, and Devanagari hook/revelation/value signals.
- Scores hooks strongly only when they occur at the opening instead of anywhere
  in the candidate, reducing false high scores.
- Added incomplete-ending and filler-opening penalties.
- Replaced all-or-nothing overlap rejection with measured 50% overlap suppression.

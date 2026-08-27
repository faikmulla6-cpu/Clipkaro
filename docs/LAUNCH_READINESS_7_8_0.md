# ClipKaro 7.8.0 — Launch-Candidate Readiness

**Status:** code-complete launch candidate; public paid launch remains fail-closed until the external prerequisites below are supplied and validated.

This document is the canonical handoff for taking the repository from a tested local/private build to a public paid deployment. It deliberately separates **software readiness** from **operator-controlled production readiness**. Do not fill missing legal, domain, email, payment, or provider values with placeholders merely to make a preflight green.

## 1. What is implemented

### Product and account flow

- Next.js App Router frontend with signup/login/logout, persisted sessions, email-verification UX, password reset, dashboard, upload, projects, Creator Studio, exports, pricing, templates, brand kit, calendar drafts, settings/help and legal/privacy surfaces.
- FastAPI backend with Argon2id password hashing, revocable persisted sessions, JWT transport, CSRF protection and resource ownership checks.
- Verified-email enforcement before creator compute so unverified users cannot consume upload/ASR/render resources through the normal customer API.
- SQLite WAL persistence with quota reservations, worker job claims, recovery and durable job/transcript/export records.

### Media pipeline

- Authenticated streaming upload flow with extension/MIME checks, UUID storage names, plan-aware limits, ClamAV production scanning and FFprobe validation.
- Public edge request-body ceiling plus storage-backed multipart spooling so malformed/oversized uploads are bounded without breaking valid near-limit uploads.
- API-first ASR: Groq primary and Cloudflare fallback for the default route; provider-native word timing; durable ASR latency and provider-attempt/fallback observability.
- Explicitly gated Roman-Hinglish/ElevenLabs route with persisted routing decisions, Roman V3 and Display V1 exactly-once protection. The generic production example leaves this private rollout **disabled**.
- Ranked clip suggestions and Creator Studio editing.
- Explicit language re-analysis is durable and bounded (maximum 3 corrections per source in 24 hours), reuses the original minute reservation instead of double-charging a completed source, and preserves already-exported historical moments as hidden superseded records.
- Re-analysis and automatic pipeline upgrades will not mutate project transcript/clip state while an export is actively rendering. Expired source media blocks new re-analysis/export instead of creating doomed worker jobs, while project/export history remains visible.
- FFmpeg/LibASS export with validated video/audio streams and distinct Kinetic, Clean, Bold, Minimal and India Pop render personalities. Production containers install system Noto/Liberation font packages; release artifacts intentionally do not distribute font binaries.
- Download and expiry cleanup flow with truthful queued/processing/failed/expired export states. Expiry is enforced at read/download time rather than relying only on the hourly cleanup sweep, and persisted media paths are confined to ClipKaro's configured upload/export storage roots before reads or deletion.

### Billing and fair access

- Free, Mini Pass, Creator, Growth, Pro and Agency plan catalog with server-authoritative entitlements.
- Atomic minute/export reservations and pre-ASR quota rejection.
- Razorpay Orders for one-time Mini Pass and Subscriptions for recurring tiers.
- Backend checkout creation, browser callback signature verification and server-side provider payment confirmation before one-time entitlement activation.
- Signed Razorpay webhook verification with atomic provider-event claims, crash-recoverable in-progress claims and duplicate/replay protection before entitlement side effects.
- Captured `payment.captured` / `order.paid` webhook recovery for one-time purchases when the browser callback is lost. `payment.failed` and `payment.authorized` are retained only as operational state and can never grant Mini Pass entitlement before provider capture.
- Recurring subscription lifecycle synchronization handles authenticated/activated/charged/updated/pending/paused/resumed/halted/cancelled/completed/expired states. Provider `notes` are never entitlement authority; server-created checkout bindings plus provider Plan IDs are used instead. Out-of-order events cannot roll a newer plan backward and terminal subscription states cannot be reactivated by stale events.
- Checkout creation is serialized per user and short-lived unfinished Razorpay checkout objects are reused, limiting duplicate paid commitments caused by double-clicks, retries or multiple tabs.
- Any new/increased paid commitment requires the user's acceptance of the current Terms, Privacy Notice and Refund Policy. Users can still reduce/cancel spend without being forced to accept newer terms.
- Production live checkout remains blocked until required legal/operator and payment configuration is complete. A deliberately explicit local-development live-payment opt-in exists for merchant integration testing and is rejected by production boot configuration.

### Security and operations

- Caddy TLS edge with HSTS, CSP, anti-framing, content-type, referrer and permissions headers.
- API/worker/web containers run read-only with dropped Linux capabilities, no-new-privileges, resource/PID limits and isolated service networks. The frontend uses Node 24 LTS; backend runtime installs FFmpeg, Tesseract, Noto and Liberation fonts from the OS package manager.
- API is not published directly by the production Compose file.
- ClamAV runs as a private scanning sidecar with no public port.
- Demo-user seeding defaults off.
- Provider credentials required for media processing are worker-side in production rather than copied into the public API process.
- Production preflight reports secret-safe readiness and fails closed on unsafe production configuration. Request IDs are syntax/length bounded before reflection, and security headers are applied consistently even to early middleware denials.
- Production worker image selection is explicit: `WORKER_IMAGE_TARGET=media` for the default API-provider ASR media path, while an intentionally chosen local faster-whisper/WhisperX deployment must rebuild with `WORKER_IMAGE_TARGET=worker`.
- `scripts/backup-production.sh` creates a consistent SQLite online backup, verifies it and copies it outside the Docker volume. An independent/off-host copy is still required operationally.
- `scripts/production-smoke.py` performs a secret-free HTTPS/edge/health/header smoke test after deployment.

## 2. Security dependency floor in this candidate

The launch candidate pins framework/parser versions above the reviewed security floors used by this repository:

- FastAPI `0.141.1`
- Starlette `1.3.1`
- python-multipart `0.0.31`
- PyJWT `2.13.0`
- Next.js `16.3.3`
- React / ReactDOM `19.2.7` or newer within the lockfile
- PostCSS `8.5.23` or newer
- Nanoid `3.3.18` or newer
- Sharp `0.35.0` or newer (currently locked to `0.35.4`)

The release verifier checks these floors. Dependency advisories change over time, so run a fresh dependency/security audit again immediately before public deployment and during routine maintenance.

## 3. Intentionally NOT fabricated in the repository

The following are real-world operator inputs and must be supplied privately at deployment time:

- purchased production domain and DNS
- HTTPS/ACME email
- actual legal operator/business name and postal address
- real customer-care email/phone
- real grievance officer/name/email/phone
- privacy/legal contact mailbox
- GSTIN/PAN only when actually applicable and correct
- rotated production `SECRET_KEY`
- rotated provider credentials
- `PRODUCTION_CREDENTIALS_ROTATED=true` only **after** real rotation is complete
- verified Resend sending domain and `EMAIL_FROM` (or a deliberately configured SMTP fallback)
- Razorpay LIVE key pair belonging to the production merchant account
- strong Razorpay webhook secret and public HTTPS webhook registration
- real production provider credentials in the worker environment

Production readiness is supposed to stay red until these are real.

## 4. Required external launch validation

### A. Domain / TLS

1. Point the real domain to the VPS.
2. Set `DOMAIN`, `ACME_EMAIL`, `APP_PUBLIC_URL`, `FRONTEND_URL` and strict CORS origin to the real HTTPS origin.
3. Start the production Compose stack.
4. Run:

```bash
python scripts/production-smoke.py https://YOUR_REAL_DOMAIN
```

5. Confirm HTTPS, HSTS and CSP at the public edge.

### B. Transactional email

1. Verify the production sending domain in Resend.
2. Set a real sender such as `ClipKaro <verify@your-domain>`.
3. Create a new normal user.
4. Confirm the email reaches a real inbox.
5. Click the verification link on the production HTTPS site.
6. Confirm the account becomes verified and can start creator processing.
7. Exercise resend cooldown, expired token and password-reset delivery once.

### C. Razorpay LIVE

Before public paid traffic, configure the real legal particulars and register:

```text
POST https://YOUR_REAL_DOMAIN/api/v1/billing/razorpay/webhook
```

with the same private webhook secret configured on the API.

Then validate at least:

1. Mini Pass LIVE purchase: order → checkout → captured provider truth → entitlement.
2. Browser-return-loss scenario: signed captured webhook still activates the matching Mini Pass exactly once.
3. One recurring plan LIVE subscription: checkout → authenticated (no entitlement before charge) → activated/charged lifecycle → entitlement sync.
4. Renewal webhook/sync on the recurring plan.
5. Pause/resume plus pending/halted behavior and expiry of a non-paying period.
6. User cancellation / cycle-end state.
7. Duplicate and deliberately out-of-order webhook delivery cannot duplicate or roll back entitlement.
8. Bad webhook signature is rejected.
9. Mismatched amount/currency/order cannot activate a one-time entitlement.
10. `payment.failed` / `payment.authorized` one-time events do not grant entitlement; only captured provider truth does.

Do not publicly advertise recurring billing as fully validated until the real merchant lifecycle above has been observed.

### D. Media/provider smoke

Using a verified production account:

1. Upload one short supported owned video.
2. Confirm ClamAV scan succeeds.
3. Confirm a `process_video` worker job completes.
4. Confirm ASR provider trace/latency is present for the new job.
5. Open suggested clips in Creator Studio.
6. Export one 720p and one entitled 1080p clip where applicable.
7. Confirm FFprobe/playability and download through the public domain.
8. Confirm the source/output expiry policy behaves as configured.

Do not enable full public Hinglish automatically. The generic production environment is intentionally legacy/default-route only; any private Roman-Hinglish cohort remains a separate controlled rollout decision.

## 5. Production commands

Create a private deployment `.env` from `.env.production.example`. Keep `WORKER_IMAGE_TARGET=media` with the launch-default `ASR_MODE=api`; the media job still needs scanning/FFmpeg/rendering even though transcription is provider-backed. Only a deliberate legacy/local faster-whisper or WhisperX deployment should set `WORKER_IMAGE_TARGET=worker` and rebuild the worker image. Then:

```bash
docker compose -f docker-compose.hostinger.yml config
docker compose -f docker-compose.hostinger.yml build --pull
docker compose -f docker-compose.hostinger.yml up -d
docker compose -f docker-compose.hostinger.yml ps
```

Run the authenticated product preflight from an authorized account and require both processing readiness and paid-launch readiness before opening paid public traffic.

### Backups

Create a consistent DB backup:

```bash
./scripts/backup-production.sh
```

Copy every production backup to independent/off-host storage. A backup left on the same VPS does not protect against VPS loss. Perform and document a restore rehearsal before launch or immediately after the first production backup. `scripts/restore-production.sh` validates the backup (and checksum when present), takes a fresh safety backup, stops API/worker/web writers, replaces SQLite offline, removes stale WAL/SHM sidecars, re-validates integrity and restarts services. It requires the explicit `RESTORE_CONFIRM=RESTORE_CLIPKARO` guard.

## 6. Verification required on a dependency-complete build machine

Before the public deployment artifact is promoted, run:

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
cd ../frontend
npm ci
npm run build
cd ..
python scripts/verify-release-static.py
```

Also run the project's frontend trust/static checks and a current dependency audit. Do not waive failures merely to create a release.

The static release verifier is a guardrail, not a substitute for pytest, the Next production build, container build, real provider smoke tests, real email delivery or real Razorpay webhooks.

## 7. Single-VPS scaling boundary

The supplied production topology is deliberately conservative:

- one API service
- one isolated media worker
- SQLite WAL on a persistent volume
- persistent local media storage with cleanup

Do not add multiple API replicas against this SQLite/job-claim architecture without a deliberate migration. Before horizontal scaling, move durable relational state to PostgreSQL and the job queue to a multi-worker queue/redis-backed design; move retained media to object storage where appropriate.

## 8. Release artifact hygiene

A public/deployment source artifact must NOT contain:

- `.env` or private environment backups
- API/provider/Razorpay/Resend/JWT secrets
- local user database
- uploads, exports, audio/video, logs
- local account/session/verification data
- qualification corpora/evidence containing creator media
- `.next`, `node_modules`, Python virtualenvs/caches or test caches

Use the provided launch-candidate packaging step and then scan the staged artifact—not just the working directory—for secrets before handing it to another operator or server.

## 9. Go / no-go gate

**GO** only when all of these are true:

- dependency-complete backend tests pass
- Next production build passes
- release static verifier passes
- container build/Compose configuration passes
- secret scan of the final staged artifact passes
- production preflight processing readiness passes
- production preflight paid-launch readiness passes
- real Resend inbox verification passes
- real Razorpay LIVE Mini Pass and recurring lifecycle validation passes
- public HTTPS smoke passes
- production upload → ASR → clip → edit → export → download smoke passes
- first DB backup is copied off-host and restore procedure is understood
- real legal/operator/customer-care/grievance details are published

Anything else is a **launch candidate**, not a completed public paid launch.

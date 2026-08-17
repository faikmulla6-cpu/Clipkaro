# Production preflight

`GET /api/v1/system/preflight` is an authenticated, secret-safe readiness report.
It intentionally separates media-processing readiness from public paid-launch readiness.

## Top-level decisions

- `ready`: whether ClipKaro can safely accept media-processing work. This is kept backward-compatible with Creator Studio and does **not** fail merely because billing/email/legal providers are unavailable.
- `paid_launch_ready`: production-only fail-closed decision. This is true only when every required processing check plus transactional email, Razorpay, and legal/operator configuration passes.
- `status`: `ready`, `processing_ready`, or `blocked`.
- `blockers`: sanitized paid-launch blockers. No hostnames, credentials, provider response bodies, tokens, passwords, or secret values are returned.
- `warnings`: non-blocking degradation, currently including Groq when deterministic local ranking can safely take over.

## Component checks

### Production configuration policy
Before provider probes can make paid launch ready, ClipKaro requires a strong production `SECRET_KEY`, HTTPS public URL/CORS, a configured transactional-email path (Resend preferred or SMTP fallback), complete Razorpay shape, and `PRODUCTION_CREDENTIALS_ROTATED=true`. Media-provider secrets live in the isolated worker and are verified through its secret-free heartbeat. The rotation flag must only be set after any credential exposed in plaintext has actually been replaced. The component reports blocker codes only and never secret values.


### FFmpeg / FFprobe
Runs the existing executable discovery/version probe. Both binaries must be runnable.

### Persistent storage
Performs a real create → write → fsync → delete probe in `STORAGE_ROOT`; `os.access()` alone is not trusted.

### ClamAV
Uses clamd's side-effect-free `PING` command over the private scanner network. Production upload scanning fails closed when the scanner is unconfigured or unreachable.

### Media worker
The isolated worker persists a heartbeat in shared SQLite. The API rejects missing/stale heartbeats instead of assuming an idle worker is alive. Defaults:

- heartbeat every 5 seconds
- stale after 30 seconds

The worker heartbeat also reports sanitized capabilities for the active ASR mode, optional local Whisper/alignment runtime, Hinglish route, and semantic-ranking provider.

### API ASR / optional local Whisper
The production deployment defaults to `ASR_MODE=api`. In that mode the worker must report usable Groq and/or Cloudflare ASR configuration and provider-native word timing support; faster-whisper/WhisperX is not required to process production jobs. The local/qualification mode remains available separately and can require the pinned WhisperX runtime for benchmark evidence.

### Transactional email
Resend is the preferred production path. SMTP remains a supported fallback. Preflight reports only sanitized readiness/error categories and never returns provider keys, SMTP credentials, host secrets, or response bodies.

### Razorpay
Requires Key ID, Key Secret, and webhook secret to be present, then performs a bounded read-only `GET /v1/plans?count=1` authentication probe. It creates no order, plan, subscription, or payment state and returns no provider response body.

### Legal paid-launch readiness
Reuses the existing legal/operator fail-closed configuration checks. Missing operator/customer-care/grievance particulars block `paid_launch_ready` without exposing values that are not already public legal data.

### Groq
The worker periodically performs a read-only `/openai/v1/models` probe and confirms that at least one configured ranking model is available. Groq degradation is a warning rather than a processing blocker because ClipKaro already has deterministic local ranking fallback. Credential values are never persisted to heartbeat state.

## Probe rate control

Preflight is safe to call from Creator Studio without causing one provider login per page load:

- ClamAV result cache: 10 seconds
- SMTP result cache: 60 seconds
- Razorpay result cache: 60 seconds
- Groq worker probe: every 300 seconds

All network probes are bounded by `PREFLIGHT_NETWORK_TIMEOUT_SECONDS` (default 8 seconds) and unexpected errors become sanitized fail-closed statuses instead of HTTP 500 provider traces.

## Release evidence

`backend/tests/test_production_preflight.py` protects the response split, secret-safety contract, durable heartbeat, stale-worker handling, provider probe wiring, and launch blockers. It is included in Critical Backend Invariants and as an explicit Fresh Launch QA evidence check.

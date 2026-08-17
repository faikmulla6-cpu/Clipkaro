# ClipKaro 7.8.0 — Release Validation Record

**Candidate date:** 2026-08-16  
**Artifact class:** sanitized source launch candidate, not evidence of a completed public paid launch.

## Validation completed in the handoff environment

The following checks were executed after the final hardening changes in the source tree:

- Python bytecode compilation for `backend/app`, `backend/tests`, and `scripts`: **PASS**.
- Release static verifier: **PASS** (124 checks green at the latest source-tree run).
- Pure dependency-free safety tests: **PASS** (6/6): 3 storage-confinement cases (correct-area acceptance, traversal rejection and symlink escape rejection) plus 3 persisted-public-error sanitization cases.
- Frontend trust contracts: settings persistence, analytics truth, billing lifecycle, email verification, security foundation, legal/privacy, behavioral learning, landscape reframe, and release identity: **PASS**.
- Shell script syntax (`bash -n`): **PASS**.
- Production/local Compose YAML parsing: **PASS**.
- Production Compose environment-reference coverage against `.env.production.example`: **PASS**.
- Offline production environment validator is fail-closed for HTTPS/domain binding, Razorpay LIVE mode, worker/ASR target pairing, Stage-1 allowlist consistency, transactional email and real legal/operator particulars.
- Existing local SQLite `PRAGMA integrity_check`: **ok**; foreign-key violations: **0**.
- Source privacy scan for developer-specific absolute Windows/macOS paths after cleanup: **PASS** for the release source scope.
- Sanitized release packaging performs an exact-value scan against private local environment values without printing them and rejects generic credential patterns, private runtime state, media, databases, logs, caches, and font binaries.

## High-risk flows specifically hardened

### Billing

- Razorpay server-side checkout creation and HMAC callback verification remain authoritative.
- Mini Pass activation requires captured provider truth and validates payment/order/amount/currency.
- Signed `payment.captured` / `order.paid` webhooks can recover a captured one-time entitlement if the browser callback is lost.
- Webhook payload persistence redacts avoidable payer-sensitive fields. Razorpay event IDs are atomically claimed before entitlement side effects; concurrent duplicates receive a retryable response and stale processing claims can be reclaimed after a process crash.
- Subscription entitlement authority is server-bound (ClipKaro checkout + Razorpay Plan ID), not provider `notes`. Out-of-order webhook events cannot roll back a newer plan and terminal states are monotonic. Pre-charge `subscription.authenticated` cannot grant paid access.
- One-time `payment.failed` / `payment.authorized` events update operational checkout state only; Mini Pass entitlement still requires captured provider truth.
- Per-user checkout serialization and short-lived checkout reuse reduce accidental duplicate orders/subscriptions from retries, double-clicks or multiple tabs.
- Duplicate checkout regression coverage verifies that repeated Mini Pass and recurring-plan checkout requests reuse the same provider object instead of creating a second paid commitment.
- Replaying an already-verified checkout reports the customer's current entitlement state rather than treating historical payment truth as a permanently active plan. Recurring browser verification requires the provider subscription to be `active`, and webhook checkout state follows the actual local entitlement.
- New/increased paid commitments require current legal acceptance; downgrade/cancellation paths remain available without forcing new acceptance.
- Production legal/operator readiness remains fail-closed. Local LIVE Razorpay testing is an explicit development-only opt-in and production boot rejects it.

### Media / project lifecycle

- Upload is scan-first, storage-bounded, ownership-scoped and durably queued.
- Provider route decisions are persisted before worker execution.
- ASR provider latency/attempt/fallback observability is durable for new jobs.
- Explicit language re-analysis is durable, bounded, restart-safe and does not double-charge source minutes after successful original processing.
- Exported historical clips are preserved as superseded history when a source is re-analysed; current project surfaces hide superseded clips.
- Re-analysis/automatic pipeline upgrade is blocked while an export is active.
- Expired source media cannot create new re-analysis/export jobs; historical metadata/exports remain truthful. Ready exports are denied after their expiry timestamp even before the cleanup sweep deletes bytes.
- Persisted source/output filesystem paths are resolved and confined to the configured private upload/export roots before serving or deletion, including symlink/traversal escape protection.
- Analytics source-minute aggregation avoids clip/export join multiplication.
- Caption styles remain distinct and frozen; production uses OS-managed Noto/Liberation fonts rather than distributing font binaries in the release artifact.
- Request IDs are bounded before reflection and security headers are added to both normal responses and early auth/rate-limit denials.
- Persisted media/render failures are converted to user-safe diagnostics before database/UI exposure so FFmpeg/provider stderr and absolute host paths stay in server logs rather than customer-facing state.
- Production Compose defaults to `WORKER_IMAGE_TARGET=api`; local faster-whisper/WhisperX use requires the explicit heavyweight `worker` image target.

## Validation that still MUST run on a provisioned build/deployment machine

This environment does not contain the full installed Python/Node dependency trees or Docker daemon, so it cannot truthfully provide these final external proofs:

1. `python -m pip install -r backend/requirements-dev.txt` followed by the complete `pytest` suite.
2. `npm ci && npm run build` for the Next.js production bundle.
3. Fresh package/dependency advisory scans after install.
4. `docker compose -f docker-compose.hostinger.yml config` and image builds.
5. Production/staging boot with private rotated secrets and ClamAV health.
6. Real Resend sending-domain/inbox verification after the production domain exists.
7. One controlled Razorpay LIVE Mini Pass and one recurring subscription lifecycle, including signed public webhooks.
8. Public HTTPS upload → ASR → clips → edit → export → download smoke test.
9. Production backup plus restore rehearsal using `scripts/backup-production.sh` and the explicit/offline/integrity-checked `scripts/restore-production.sh`.

## Release decision

The sanitized ZIP is suitable as the **next deployment/build candidate**. It must not be represented as a completed public paid launch until all external gates in `LAUNCH_READINESS_7_8_0.md` pass with the real domain, legal particulars, rotated credentials, payment webhook, email sender, and dependency-complete builds.

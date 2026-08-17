# QA report — Launch Edition 7.8.0

## Certification status

**Status: PENDING FRESH RUN**

This document is the live launch-certification record for ClipKaro AI 7.8.0. It must never inherit a PASS result from an older release. The historical 2.0.1 report is preserved at `docs/archive/QA_REPORT_2.0.1.md` and is not valid evidence for the current product.

Current product version sources:

- Backend: `backend/app/core/version.py` → `7.8.0`
- Frontend: `frontend/package.json` → `7.8.0`
- Certification target: the exact `TESTED_SHA` checked out by the Fresh Launch QA workflow; no stale baseline SHA is accepted.

The final certified SHA is intentionally **not written by hand**. The dedicated `Fresh Launch QA` workflow records the exact tested Git SHA and source tree, app versions, workflow identity, backend JUnit evidence, npm audit evidence, Docker image identities, UTC timestamp, every mandatory check outcome and a tamper-evident evidence SHA-256. The immutable `launch-qa/QA_REPORT.md` workflow artifact says `CERTIFIED` only when the complete mandatory matrix passes. This tracked file remains `PENDING FRESH RUN`: changing tracked source after certification would create a new Git SHA that was not the SHA tested.

## Mandatory fresh-launch matrix

A 7.8.0 certification requires all of the following on the exact tested SHA:

1. **Release identity**
   - backend and frontend versions are identical
   - expected release version is `7.8.0`
   - `TESTED_SHA` is a full 40-character SHA and equals checked-out `HEAD`
   - working tree starts from a clean checkout and tracked source is unchanged after all checks
   - generated evidence records the exact tested Git SHA and Git tree
   - stale current-release QA references such as `Launch Edition 2.0.1` are rejected outside `docs/archive/`

2. **Backend correctness**
   - Python application/tests/scripts compile
   - installed Python dependencies pass `pip check`
   - complete backend pytest suite passes under `APP_ENV=test` and fixture transcription
   - no test is silently selected out by a release-specific allowlist

3. **Frontend/product trust contracts**
   - Settings persistence/trust contract
   - Analytics truth contract
   - Billing lifecycle contract
   - Email-verification contract
   - Security-foundation contract
   - Legal/privacy launch contract
   - Behavioral-learning contract
   - Landscape manual-reframe contract
   - release-identity contract before and after locked dependency installation
   - optimized Next.js production build

4. **Dependency/security baseline**
   - production npm dependency audit JSON is preserved and has zero high/critical vulnerabilities
   - package-lock based install is used (`npm ci`)
   - missing/malformed audit evidence cannot be treated as success

5. **Production deployment configuration**
   - production-preflight regression proves secret-safe processing vs paid-launch readiness, durable worker heartbeat, ClamAV/SMTP/Razorpay probes, legal gating and non-blocking Groq fallback semantics
   - `docker compose -f docker-compose.hostinger.yml config --quiet`
   - production Caddyfile validates with the pinned Caddy image
   - production API Docker image builds from the exact checkout
   - production media-worker Docker image builds from the exact checkout
   - built worker validates the pinned WhisperX/faster-whisper runtime before certification
   - frontend production Docker image builds from the exact checkout
   - API/worker/frontend Docker image IDs are recorded in immutable evidence

6. **Evidence integrity**
   - every mandatory check outcome is written to machine-readable JSON
   - a Markdown summary is generated from the same outcomes
   - evidence is uploaded even when a mandatory check is red or execution is blocked
   - an immutable canonical mandatory-check set prevents subset-based false certification
   - evidence carries a SHA-256 integrity digest which enforcement recomputes
   - final enforcement fails the workflow when any required check is not successful

## Launch gates kept separate from build certification

A clean application/build/deployment-candidate certification does not manufacture evidence for external or empirical gates:

- **Real ASR acoustic qualification (#21):** the Hindi/Marathi/Hinglish harness is merged, but the real faster-whisper verdict remains open.
- **Landscape podcast framing verdict (#22):** the 30-export harness is merged, but representative real-footage evidence remains open.
- **GitHub main ruleset (#25):** source governance exists, but repository-side branch protection is a separate administrative control.
- **Live ₹59 Mini Pass payment:** **PASSED on 11 Aug 2026** for the one-time Razorpay live-mode path: captured payment, paid order, server-side verification, Mini Pass activation, 30-day validity and usage preservation. Evidence is recorded in `docs/PAYMENT_LIFECYCLE_STATUS.md` and `docs/evidence/CLIPKARO_V7.8_LOCAL_PAYMENT_LIFECYCLE_REPORT.md`. This does **not** certify recurring subscriptions or public webhook delivery.
- **Recurring billing/webhook lifecycle:** **PENDING** — real public webhook delivery/replay, recurring mandate activation, renewal and cycle-end cancellation remain unproven.
- **Production secrets/operator deployment (#30):** paid launch still depends on actual operator/grievance particulars, SMTP, rotated Razorpay/Groq credentials, ClamAV/worker health, HTTPS and real end-to-end deployment verification.

These gates remain visible so “7.8.0 build certified” cannot be misread as “every public-launch dependency is complete.”

## Fresh-run evidence

No certification result is recorded here yet. After the dedicated workflow produces a complete green run, this section must record:

- tested SHA
- workflow run ID
- UTC certification timestamp
- backend test count/result
- every frontend trust-contract/build result
- dependency audit result
- Compose/Caddy validation result
- API/worker/frontend image-build results and worker alignment-runtime result
- any warnings that did not change the pass/fail decision

Until then, **7.8.0 is not certified by this document**.

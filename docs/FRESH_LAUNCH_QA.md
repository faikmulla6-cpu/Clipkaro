# Exact-SHA Fresh Launch QA

Fresh Launch QA is ClipKaro's build/deployment-candidate certification. It is deliberately separate from the empirical real-ASR, real-landscape, live-production/payment, and GitHub branch-protection gates.

## Certification rule

`CERTIFIED` is possible only when one exact Git SHA completes the entire mandatory matrix on the trusted Linux x64 `clipkaro-qa` runner. An extracted ZIP, dirty checkout, missing workflow run ID, incomplete check list, unavailable Docker image identity, missing pytest/audit evidence, or runner/dependency/network prerequisite failure yields `BLOCKED`. A valid environment with a red product/build/security check yields `FAIL`.

The authoritative certification record is the immutable workflow artifact `launch-qa/QA_REPORT.md` plus `launch-qa-evidence.json`. The tracked `docs/QA_REPORT.md` intentionally remains a pending release record until an exact candidate is executed. Rewriting a tracked file to say CERTIFIED after the run would create a new Git SHA that was never tested.

## Mandatory matrix

The exact candidate must prove all of the following:

- exact 40-character `TESTED_SHA` equals checked-out `HEAD`
- clean checkout before execution and unchanged tracked source after execution
- self-hosted launch-runner prerequisites and outbound dependency/image access
- isolated Python 3.12 environment and locked backend dependency install
- backend/frontend release identity 7.8.0
- Python compile and `pip check`
- complete backend pytest suite with JUnit evidence and zero failures/errors
- production-preflight regression
- exact frontend `npm ci`
- Settings, Analytics, Billing, Email, Security, Legal/Privacy, Behavioral Learning and Landscape trust contracts
- release identity after locked frontend install
- production npm audit with zero high/critical advisories
- optimized Next.js production build
- production Compose validation
- production Caddy validation
- API Docker image build
- media-worker Docker image build
- pinned WhisperX/faster-whisper validation inside the built worker
- frontend Docker image build
- immutable identities for all three built images
- tamper-evident final evidence digest

## Evidence integrity

`generate_launch_qa_report.py` contains the canonical mandatory-check set. Supplying only a subset cannot certify the release. The report also cross-checks JUnit evidence, npm-audit JSON, Docker image identities, Git SHA/tree identity, source cleanliness and GitHub workflow metadata.

The JSON report contains an `evidence_sha256` calculated over its canonical payload. `enforce` recalculates that digest and rejects a changed or incomplete report.

## Runner command

The GitHub workflow is the certification authority because it binds evidence to a repository and workflow run ID. Before running it, validate the host with:

```bash
bash scripts/check-self-hosted-runner.sh --profile launch
```

The workflow itself additionally writes `launch-qa/execution-preflight.json`, which records the exact Git candidate, host/runtime availability, Docker daemon/Compose access, RAM/disk and required outbound registry reachability.

## Current external payment evidence

The **₹59 Mini Pass Razorpay live-mode happy path is PASSED (11 Aug 2026)** and is tracked separately from exact-SHA build certification. The evidence proves payment capture, paid order state, server-side checkout verification, Mini Pass activation and usage preservation. Full recurring subscription/webhook production evidence remains pending. See `docs/PAYMENT_LIFECYCLE_STATUS.md`.

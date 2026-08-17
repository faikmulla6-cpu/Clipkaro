# ClipKaro GitHub engineering workflow

This document defines how ClipKaro changes move from an idea or defect to `main` without losing product history or silently breaking critical systems.

## Workflow at a glance

```text
Issue
  ↓
agent/<issue>-<slug> branch
  ↓
logical checkpoint commits
  ↓
draft PR with Closes #issue
  ↓
PR Governance
  ↓
Critical Product Contracts
  ↓
full ClipKaro CI
  ↓
empirical/external QA when required
  ↓
record exact green head SHA
  ↓
ready for review
  ↓
merge pinned to expected head SHA
  ↓
post-merge main checks / deploy verification
```

## Why issues and PRs are separate records

An **issue** is the durable statement of the problem, decision, acceptance criteria and blockers. A **PR** is one implementation attempt that changes code.

Keeping these separate gives ClipKaro:

- a backlog that remains meaningful even if a PR is abandoned/replaced
- a place to track external blockers such as GitHub runner outages
- explicit acceptance criteria before implementation begins
- clean links from product risk → code change → test evidence → merge commit
- the ability to split a large issue into multiple focused PRs without losing the original goal

Merged PRs remain the implementation history. Do not squash away important engineering context merely to make the history look artificially simple.

## Risk classes

### Critical

Changes that can affect money, access, security, legal compliance, or durable state:

- Razorpay checkout/subscriptions/webhooks
- plan changes and entitlement periods
- Karo Minute/export reservations
- SQLite transaction/lock behavior
- sessions/password/email verification
- legal consent and paid-launch gates
- malware scanning / worker isolation

Critical changes require focused regression tests plus the independent Critical Product Contracts workflow.

### High

Uploads, transcription, ranking providers, rendering, durable jobs and deployment changes. These require failure/recovery/resource-limit testing as relevant.

### Medium / Low

Normal product behavior, copy, documentation and isolated UI changes. They still run the critical contracts because a supposedly unrelated edit can alter shared routing/build/configuration.

## Issue discipline

An issue should contain the problem and acceptance contract, not a predetermined code patch only. Include:

- user/business impact
- current behavior
- desired behavior
- concurrency/retry/failure cases
- existing-account/data compatibility
- tests/evidence required
- rollout/rollback for production-impacting work

QA issues must define pass/fail thresholds before evidence is collected.

## Branch and commit discipline

One primary issue per branch:

```text
agent/<issue-number>-<slug>
```

Use multiple coherent commits where it improves review/auditability. Examples:

1. schema/service primitive
2. API enforcement
3. frontend behavior
4. regression tests
5. deployment contract/docs

A later fix discovered by CI should be its own explanatory commit when that history is useful. Avoid dozens of meaningless retry commits.

## Pull request lifecycle

Open a draft PR early. The PR template requires:

- closing issue link
- risk class
- critical invariants touched
- validation evidence
- DB/migration compatibility
- security/privacy review
- rollout/rollback
- exact tested head SHA

A PR stays draft while required evidence is missing. A workflow that never received a runner is **not** a green test run.

## CI layers

### PR Governance

Uses `pull_request_target` and trusted base-branch code. New PRs must:

- link a tracking issue with a closing keyword
- follow the issue-number branch convention
- retain risk/validation/rollback sections

Legacy PRs that existed before the process cutover are grandfathered.

### Critical Product Contracts

Runs independently on every PR and `main`. It explicitly names the backend tests that protect:

- core API/quota behavior
- subscription lifecycle
- SQLite contention/atomicity
- email verification
- auth/session/security foundation
- legal/privacy paid-checkout gating

It also runs the billing, email-verification, security and legal frontend trust contracts.

This lane exists so an unrelated PR cannot rely only on “the full suite probably covers billing.”

### ClipKaro CI

Runs the complete backend suite plus all frontend trust contracts, production Compose/Caddy validation and the production Next build.

Only PR events, `main` pushes and explicit manual runs are used. Redundant `agent/**` push runs are intentionally removed, and concurrency cancels stale runs when a newer PR commit arrives.

### Empirical qualification

Some launch questions cannot be proved by deterministic CI: real ASR accuracy, real landscape framing prevalence, production hardware throughput, live provider credentials, etc. These stay as separate issues/workflows and block only the decision they actually measure.

## Exact-SHA merge rule

The final green workflow run authorizes **one commit SHA**.

Before merge:

1. note the exact PR head SHA
2. ensure required checks passed on that SHA
3. ensure no later commit was pushed
4. confirm base changes do not invalidate the result
5. merge using GitHub's expected-head-SHA protection

If the head changes, rerun. Never say “CI was green earlier” after changing code.

## Hotfix procedure

For a production P0/P1:

1. open a bug issue immediately with impact and rollback notes
2. create `agent/<issue>-<slug>` from current `main`
3. add a regression test reproducing the incident when feasible
4. keep the patch minimal
5. run Critical Product Contracts and full CI
6. merge exact tested SHA
7. verify `main` checks
8. document production verification and incident follow-up on the issue

Do not bypass billing/auth/quota tests because the fix is urgent.

## GitHub repository settings

Source control can define workflows, but GitHub Settings/Rulesets must make them merge requirements. Configure `main` to:

- require pull requests
- block force pushes/deletion
- require branches to be current before merge
- require `PR Governance`
- require `Critical Backend Invariants`
- require `Critical Frontend Contracts`
- require the normal `backend` and `frontend` CI jobs

If GitHub Actions has an infrastructure outage, keep PRs draft/open and track the outage in an issue. Do not disable required checks to force a merge unless there is a separately documented production-emergency decision and equivalent evidence from another trusted environment.

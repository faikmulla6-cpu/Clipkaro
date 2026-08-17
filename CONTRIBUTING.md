# Contributing to ClipKaro

ClipKaro handles billing, usage quotas, authentication, uploaded media and paid AI compute. Changes therefore follow an **issue-first, PR-first, exact-SHA** workflow.

## 1. Start with an issue

Every non-trivial change starts from a GitHub issue with:

- one primary outcome
- severity/risk class
- acceptance criteria
- failure/concurrency/compatibility scenarios
- required evidence
- rollout/rollback notes for production-impacting changes

Use the repository issue forms instead of a blank issue. Empirical QA thresholds must be written before the run starts.

## 2. Create a focused branch

Use:

```text
agent/<issue-number>-<short-slug>
```

Example:

```text
agent/19-github-process-upgrade
```

Do not implement normal work directly on `main`.

## 3. Commit in logical checkpoints

Prefer small, reviewable commits that each represent one coherent step: schema/service, API, UI, regression tests, deployment contract, docs, etc.

Avoid both extremes:

- one giant opaque commit containing the whole feature
- dozens of meaningless “fix typo / try CI again” commits

Never rewrite history merely to hide a failure that materially informed the implementation. The PR conversation and commit history are part of the engineering audit trail.

### Merge strategy

For normal feature, hardening, migration and infrastructure PRs, prefer a **merge commit that preserves the PR's logical checkpoint commits**. This keeps the implementation history inspectable after merge.

Use squash merge only for genuinely trivial changes where the individual commits add no useful engineering history. Do not squash a multi-stage billing/security/data migration merely to make `main` look artificially linear.

## 4. Open a draft PR early

The PR must link its issue with `Closes #<number>` (or `Fixes` / `Resolves`) and use the repository PR template.

Keep the PR draft while:

- acceptance criteria are incomplete
- required external/empirical evidence is missing
- migrations/rollback are unresolved
- CI is red
- GitHub Actions never executed the jobs

A product failure discovered by QA is evidence. Do not relabel it as an infrastructure problem unless the workflow truly failed before testing the product.

## 5. Critical invariants

Any change can accidentally break a critical area, so every PR runs a separate **Critical Product Contracts** workflow in addition to the full suite.

Critical invariants include:

- Razorpay order/subscription/webhook lifecycle
- immediate upgrades / cycle-end downgrades
- Karo Minute and export reservation exactly-once accounting
- SQLite atomicity and lock recovery
- revocable sessions / password reset / email verification
- legal acceptance before paid checkout
- malware scanning / isolated worker boundaries
- export/media access and integrity

Do not skip these tests because a change “should not affect billing.” That assumption is exactly what the independent gate is designed to challenge.

## 6. Merge the exact tested SHA

Before moving a PR out of draft:

1. run required CI on the final head
2. record the exact head SHA in the PR Validation section
3. inspect failures and warnings rather than rerunning until green
4. ensure `main` has not moved in a way that invalidates the result
5. merge with the expected head SHA pinned

If any code changes after the green run, the previous run no longer authorizes the merge.

## 7. Production changes

For migrations, billing, auth/security, background workers or deployment configuration, the PR must describe:

- backward compatibility
- deployment order
- rollback behavior
- failure/retry semantics
- monitoring or verification after deployment

Never include production passwords, API secrets, Razorpay secrets, SMTP passwords, user PII, or private creator media in issues, commits, PRs, tests or Actions artifacts.

## Repository protection settings

The workflows in source control provide the checks, but GitHub repository rules must also require them before merging to `main`. Recommended `main` rules:

- require a pull request before merging
- block force pushes and deletion
- require branch to be up to date before merge
- require `PR Governance`
- require both jobs from `Critical Product Contracts`
- require normal `ClipKaro CI` backend and frontend jobs
- dismiss stale approvals when new commits are pushed if multiple reviewers are used later

These GitHub-side rules are administrative settings and are not a substitute for the source-controlled test contracts.

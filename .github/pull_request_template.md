Closes #<!-- tracking issue number -->

## What changed

<!-- Keep this focused on one issue/outcome. Explain behavior, not just filenames. -->

## Why

<!-- Root cause / product or operational reason. -->

## Risk

**Risk class:** <!-- Critical / High / Medium / Low -->

### Critical invariants touched

- [ ] Billing / Razorpay lifecycle
- [ ] Karo Minutes / export reservations
- [ ] Authentication / sessions / email verification / password reset
- [ ] Legal consent / paid-checkout gate
- [ ] SQLite/data integrity/concurrency
- [ ] Upload scanning / worker isolation
- [ ] Media rendering / export/download
- [ ] None of the above

<!-- For every checked critical area, state what must remain true after this change. -->

## Validation

**Tested head SHA:** `<!-- exact SHA after final CI -->`

- [ ] Focused regression tests added/updated
- [ ] Critical Product Contracts workflow passed on this exact head
- [ ] Full ClipKaro CI passed on this exact head
- [ ] No failing check was dismissed as “unrelated” without evidence
- [ ] Manual/empirical evidence attached when the issue requires it

### Evidence

<!-- Test counts, workflow run, screenshots/artifacts, failure-injection results, etc. -->

## Database / migration / compatibility

<!-- Existing users, subscriptions, sessions, jobs, media, schema rows, config or API compatibility. Write “None” only after checking. -->

## Security / privacy / secrets

<!-- Direct API bypass, authz, CSRF, sensitive logs, provider secrets, PII, uploaded media, legal/privacy impact. -->

## Rollout / rollback

<!-- Deployment order, environment/config changes, migration sequence, monitoring, and concrete rollback path. -->

## Scope check

- [ ] Branch is focused on the linked issue; unrelated cleanup was excluded
- [ ] Commits are logical/reviewable checkpoints rather than one opaque dump
- [ ] No credentials, private media, tokens, or personal data are committed
- [ ] Documentation/operational notes are updated where behavior changed
- [ ] PR remains draft while required evidence or external qualification is pending
- [ ] Merge will use the exact final head SHA that passed required checks

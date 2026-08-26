# Stage 2J — Founder Admin Production Activation Preparation

Status: **PREPARED ONLY — NOT ACTIVATED**

This runbook prepares the read-only Founder Admin API for a later explicitly approved activation. It does not authorize merging into `modal-no-vps`, deploying Modal, setting production secrets, or changing live configuration.

## Pinned pre-activation baseline

- Founder Admin feature source: `feature/founder-admin-api` @ `3b7d3afe55bc21ca3a002becd2e62fdd0f70ffe9`
- ClipKaro `main`: `43d808f15983854206ae76de1e1e02f21556d4ee`
- ClipKaro `modal-no-vps`: `ceaaf3731975a5f9083e76190dfc1ad4eda52b17`
- Recovery `release/clipkaro-launch-v1.0.0`: `ceaaf3731975a5f9083e76190dfc1ad4eda52b17`

The production and recovery refs above must not move during Stage 2J preparation.

## Secret generation and rotation

Generate the Admin service token only on a trusted local machine:

```powershell
cd backend
python scripts/generate_founder_admin_token.py
```

The generated token is displayed once and is not written to disk. Store the same value in the server-side secret stores for ClipKaro and Founder Console. Never place it in Git, `NEXT_PUBLIC_*`, screenshots, browser storage, support tickets, chat, or example environment files.

Rotation procedure after activation:

1. Generate a new token locally.
2. Install it in Founder Console while the bridge is disabled.
3. Install the same new token in ClipKaro while `ADMIN_API_ENABLED=false` or during a controlled maintenance window.
4. Re-enable only after both sides match and smoke tests pass.
5. Remove the old value from both secret stores.

## Final activation order — requires a separate explicit GO

1. Freeze and record final candidate SHAs for both repositories.
2. Re-run all Stage 2I/2J CI gates and secret scans.
3. Promote the Founder Admin candidate toward the live ClipKaro branch only after explicit approval.
4. Deploy ClipKaro with `ADMIN_API_ENABLED=false` and the service token installed server-side.
5. Verify `/api/v1/admin/overview` returns **404** while disabled.
6. Deploy Founder Console with founder authentication configured, `FOUNDER_CONSOLE_ENABLED=false`, production HTTPS Admin URL configured, and the matching server-only token installed.
7. Verify founder login/MFA, security headers, logout, and protected-route behavior while the data bridge remains disabled.
8. Configure `admin.clipkaro.pro` only after the Founder Console deployment is healthy.
9. Set `ADMIN_API_ENABLED=true` on ClipKaro and verify authenticated GET-only Admin API smoke checks.
10. Set `FOUNDER_CONSOLE_ENABLED=true` on Founder Console and verify all read-only modules.
11. Observe logs/health. Do not add write operations during activation.

## Emergency rollback

Fastest containment path:

1. Set Founder Console `FOUNDER_CONSOLE_ENABLED=false`.
2. Set ClipKaro `ADMIN_API_ENABLED=false`.
3. Confirm Admin API returns 404.
4. Rotate/remove the Admin service token if exposure is suspected.
5. If code rollback is needed, restore the known-good ClipKaro production/recovery baseline according to the existing recovery procedure.

Disabling the bridge/API is preferred over destructive data changes.

## Production smoke checklist

After a separately approved activation:

- health endpoint remains healthy
- normal ClipKaro customer login/upload/project flows remain unaffected
- disabled gate returns 404 before activation
- missing/wrong Admin token returns 401 after activation
- all nine Admin GET endpoints return expected JSON with `Cache-Control: no-store`
- user payload excludes `password_hash`, `billing_reference`, session secrets/tokens
- audit metadata redaction remains active
- Founder Admin reads do not change tested customer business state
- Founder Console service token never appears in browser source/network-visible application code
- Founder Console login + MFA + logout pass
- all Founder Console modules render through server-side requests only

## Stage 2J stop condition

Stage 2J must stop with:

- `ADMIN_API_ENABLED=false`
- no production token installed by automation in this branch
- no Modal deployment
- no DNS change
- no merge into `modal-no-vps` or `main`

A separate explicit final approval is required before any production activation step.

# Founder Admin Stage 2G — Production Readiness Hardening

This stage remains isolated from ClipKaro production. It does not deploy, enable, or connect the Founder Admin API to production services.

## Activation invariants

- `ADMIN_API_ENABLED=false` remains the default.
- When disabled, Founder Admin configuration adds no production boot blocker.
- When explicitly enabled in production, `ADMIN_API_SERVICE_TOKEN` must be a dedicated strong server-only secret of at least 48 characters.
- The admin service token must not be reused as ClipKaro `SECRET_KEY`, Razorpay key secret, or Razorpay webhook secret.
- Configuration failures expose blocker codes only; secret values must never appear in errors or summaries.
- The Founder Admin router remains GET-only and continues to use only `fetch_one` / `fetch_all` database access.
- Founder Console must remain the only intended server-side consumer. Browser JavaScript must never receive the service token.

## Safe activation sequence (future only)

1. Keep the production API disabled while deploying code that contains the guarded Admin API.
2. Generate a new dedicated random service token outside source control.
3. Install the same token into the ClipKaro server environment and Founder Console server environment.
4. Verify the Founder Console deployment uses HTTPS and founder MFA is enabled.
5. Run the production-readiness checks and a read-only smoke test.
6. Enable `ADMIN_API_ENABLED=true` only after the above gates pass.
7. Confirm all nine endpoints remain GET-only and all responses are `Cache-Control: no-store`.

## Rollback

The immediate rollback is configuration-only: set `ADMIN_API_ENABLED=false` and restart/redeploy the API. The customer product does not depend on Founder Admin availability.

## Explicitly out of scope

- no customer-data writes
- no user deletion
- no refunds
- no subscription changes
- no quota edits
- no job retry/cancel controls
- no direct Founder Console credentials for Neon, Modal, B2, or Razorpay
- no deployment from this feature branch

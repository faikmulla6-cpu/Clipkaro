# ClipKaro Founder Admin API — Stage 2C

This contract is the narrow server-to-server bridge between the separate Founder Console and the ClipKaro backend.

## Safety state

The API is **disabled by default**. Unless `ADMIN_API_ENABLED=true` is installed privately in the backend environment, every `/api/v1/admin/*` request returns `404`.

When enabled, requests require a strong private bearer token supplied through `ADMIN_API_SERVICE_TOKEN`. The token is server-only and must never be exposed to browser JavaScript, committed to Git, placed in `NEXT_PUBLIC_*`, screenshots, logs, or support messages.

Founder Console continues to authenticate the human founder separately. Its server then calls this API with the service token.

```text
Founder browser
    -> Founder Console authentication + MFA
    -> Founder Console server
    -> Authorization: Bearer <ADMIN_API_SERVICE_TOKEN>
    -> ClipKaro /api/v1/admin/*
    -> read-only Founder Admin route handlers
```

Customer `current_user` authentication is intentionally not reused. Normal customer authentication can reconcile subscription state; Stage 2C must never trigger customer entitlement/billing writes merely because the founder viewed a dashboard.

The Founder Admin route module itself imports only `fetch_one` and `fetch_all` from the database layer and performs no business-data writes. In production, ClipKaro's existing global security middleware may still update its `security_rate_limits` bookkeeping table for the request. That operational anti-abuse counter is the only expected database mutation caused by a Founder Admin GET; users, plans, projects, jobs, usage, billing, media and audit business records remain untouched by these handlers.

## Read-only endpoints

- `GET /api/v1/admin/overview`
- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}`
- `GET /api/v1/admin/projects`
- `GET /api/v1/admin/jobs`
- `GET /api/v1/admin/billing/summary`
- `GET /api/v1/admin/usage`
- `GET /api/v1/admin/system-health`
- `GET /api/v1/admin/audit`

No Stage 2C route accepts `POST`, `PATCH`, `PUT`, or `DELETE`.

## Data minimization

The API deliberately excludes:

- password hashes
- reset/verification tokens
- auth session tokens or cookies
- Razorpay key material
- provider webhook payloads
- billing provider references from user payloads
- storage object keys and signed URLs
- Modal/provider credentials
- database credentials

Audit metadata is parsed and sensitive key names are redacted before returning it.

## Billing semantics

`verified_revenue_*` values currently come only from local `billing_checkouts` rows whose status is `verified`. Treat this as **verified checkout value**, not complete accounting revenue: subscription renewals may be represented in webhook/payment-event history without creating a new checkout row, so this metric can undercount total recurring collections.

`estimated_local_mrr_paise` is an operational estimate based on current local recurring-plan entitlements and the server-side plan catalog. The read-only endpoint does **not** call Razorpay and does not reconcile provider state. Neither metric should be presented as audited accounting or live provider truth.

## System-health semantics

Stage 2C system health performs application database reads only. It does not call external providers and does not create storage probes, jobs, billing syncs, or migrations. External provider probes remain explicitly `not_run`.

## Activation gate

Do not enable this API in production until all of the following are complete:

1. Stage 2C branch tests pass locally.
2. Review confirms the module imports only read helpers (`fetch_one`, `fetch_all`) from the database layer.
3. A strong random service token is generated outside source control.
4. The same token is installed privately in the ClipKaro backend and Founder Console server environments.
5. `ADMIN_API_BASE_URL` is configured only on the Founder Console server.
6. Founder Console still keeps `FOUNDER_CONSOLE_ENABLED=false` until the end-to-end connection is tested in staging/local isolation.
7. Production activation is a separate explicit step; merging code alone must not enable the API.

## Later controlled actions

Retries, suspensions, quota grants, subscription reconciliation, cancellations, refunds, job resets, or any other business write action are not part of Stage 2C. A later stage must add action-specific authorization, confirmation, idempotency, and audit logging before any write capability is exposed.

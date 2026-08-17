# ClipKaro Razorpay Billing — Production Setup

ClipKaro uses Razorpay Standard Checkout and keeps the Key Secret on the backend only.

## Locked products

- Mini Pass — ₹59 one-time — 25 Karo Minutes — 5 Shorts — 30-day validity.
- Creator — ₹199/month — 60 Karo Minutes — 15 Shorts.
- Growth — ₹399/month — 180 Karo Minutes — 50 Shorts.
- Pro — ₹799/month — 480 Karo Minutes — 150 Shorts.
- Agency — ₹1,999/month — 1,500 Karo Minutes — 500 Shorts.

All paid products include 1080p and watermark-free exports. Free includes 15 Karo Minutes, 2 Shorts, 720p and a watermark.

## What is automatic

1. The first checkout for Creator/Growth/Pro/Agency asks Razorpay for existing matching ClipKaro Plans.
2. If a matching live Plan is not found, ClipKaro creates it through `POST /v1/plans` and stores the returned Plan ID in `billing_plans`.
3. Monthly checkout creates a Razorpay Subscription and opens Standard Checkout in the browser.
4. Mini Pass checkout creates a Razorpay Order instead of a recurring Subscription.
5. Browser success data is never trusted by itself. `/billing/verify` validates the Razorpay HMAC signature on the server before granting access.
6. Recurring subscription state is synchronized with Razorpay when the local paid period expires, even if no webhook is available.
7. Users can schedule recurring cancellation at the end of the current billing cycle.

## Environment

Backend requires:

```env
RAZORPAY_MODE=live
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
```

`RAZORPAY_MODE` must agree with the configured Razorpay key type. The production Compose file forces the local-development LIVE-checkout opt-in off, so incomplete public legal/operator particulars remain a hard production gate. Local merchant integration testing may explicitly opt into LIVE mode, but that exception is never a production-launch bypass.

`RAZORPAY_KEY_SECRET` must never be put in frontend code or committed to Git. The delivered `backend/.env` is intentionally ignored by `.gitignore`.

## Recommended webhook

In Razorpay Dashboard create a webhook pointing to:

```text
https://YOUR-DOMAIN/api/v1/billing/razorpay/webhook
```

Use exactly the `RAZORPAY_WEBHOOK_SECRET` value from the production backend environment.

Subscribe to the lifecycle ClipKaro understands:

**One-time Orders/Payments**

- `payment.authorized`
- `payment.failed`
- `payment.captured`
- `order.paid`

Only captured provider truth can grant Mini Pass entitlement. Authorized/failed events are operational state only.

**Subscriptions**

- `subscription.authenticated`
- `subscription.activated`
- `subscription.charged`
- `subscription.updated`
- `subscription.pending`
- `subscription.paused`
- `subscription.resumed`
- `subscription.halted`
- `subscription.cancelled`
- `subscription.completed`
- `subscription.expired`

`subscription.authenticated` alone does not prove a paid period. ClipKaro binds subscription events to its server-created checkout and Razorpay Plan ID; arbitrary webhook `notes` are not entitlement authority. Provider event IDs are claimed before side effects so duplicate/replayed delivery is idempotent, and stale/out-of-order events cannot roll a newer/terminal entitlement state backward.

Webhook delivery improves immediacy, but paid-access correctness does not depend solely on the webhook because ClipKaro also re-checks Razorpay when a billing period expires.

## Production checklist

- [ ] Put rotated Razorpay credentials in the host's encrypted environment-variable settings instead of uploading `.env` publicly.
- [ ] Set `APP_ENV=production`, a unique 32+ character `SECRET_KEY`, `SEED_DEMO_USER=false`, HTTPS and the correct `CORS_ORIGINS` on the real VPS.
- [x] **PASS — 11 Aug 2026:** complete one real ₹59 Mini Pass purchase using Razorpay live mode. The provider captured ₹59, the order became `paid`, `/billing/verify` verified the checkout server-side, the account changed `free → mini_pass`, and usage was preserved. Private QA evidence is deliberately excluded from sanitized release artifacts.
- [x] **PASS — 11 Aug 2026:** verify the one-time Mini Pass entitlement is granted only after successful Razorpay payment verification.
- [ ] Complete one real recurring monthly subscription/mandate on the production candidate.
- [ ] Prove real signed webhook delivery, duplicate replay idempotency and an out-of-order recurring-event scenario on the public HTTPS webhook endpoint.
- [ ] Verify a real cycle-end cancellation against an active recurring subscription.
- [ ] Verify a real renewal charge or equivalent live recurring-cycle transition before declaring recurring billing production-ready.
- [ ] Never log the Key Secret or raw authentication headers.

Current status: **₹59 Mini Pass live payment lifecycle = PASSED; full recurring subscription/webhook lifecycle = PENDING.** See `docs/PAYMENT_LIFECYCLE_STATUS.md`.

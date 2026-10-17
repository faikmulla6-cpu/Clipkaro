# Clipkaro Billing and Karo Minutes Integrity

## Exact limits

| Plan | Source processing minutes per period | AI Short creations per period | Export policy |
|---|---:|---:|---|
| Free | 15 | 2 | 2 standard exports |
| Mini Pass (one-time, 30-day maximum) | 125 | 5 | Unlimited exports and re-exports |
| Creator (subscription) | 60 | 15 | Unlimited exports and re-exports |
| Growth (subscription) | 180 | 50 | Unlimited exports and re-exports |
| Pro (subscription) | 480 | 150 | Unlimited exports and re-exports |
| Agency (subscription) | 1500 | 500 | Unlimited exports and re-exports |

Karo Minutes count uploaded **source video duration**, not the length or number of exported clips. An uploaded source consumes one AI Short creation, regardless of how many ranked candidate moments it produces. A re-analysis of the same completed source cannot charge the original source again. New uploads can reserve quota until processing reaches a terminal state. The database is authoritative for concurrent quota reservations and releases.

## Billing-cycle behavior

- Free: usage period is the calendar month (UTC).
- New Mini Pass: new verified one-time purchase has a unique, independent usage ledger; does **not** inherit Free or previous passes.
- New recurring subscription: uses the newly verified provider subscription reference and current period start; does **not** inherit Free, Mini Pass, or an unrelated subscription's usage.
- Immediate upgrade inside the **same subscription and billing cycle**: carries consumed minutes and Short reservations. This prevents buying an upgrade to reset already-used credits during the same paid cycle.
- Renewal of the same plan: new provider cycle start yields a fresh usage period. Previous cycle remains auditable.
- Scheduled downgrade: current limits continue until the provider cycle changes; new cycle starts at the new tier with new credits.
- Cancellation: Clipkaro requests end-of-cycle cancellation, which keeps existing paid benefits until the end. **Immediate** provider cancellation is a distinct terminal state and can end access immediately. The recorded provider status is authoritative; never restore cancelled entitlements from a screenshot.
- Failed/incomplete processing: DB reservation triggers decide whether to release reserved minutes/Short credits; successful source processing is finalized. Re-exports do not reserve new source minutes.
- Paid plan has no ordinary export-count cap, but source processing is always bounded by the plan's Karo Minutes and Short creation counts.

## Regression coverage

`backend/tests/test_subscription_lifecycle.py` tests scheduled changes, provider ordering/idempotency and same-cycle upgrades.
`backend/tests/test_plan_usage_integrity.py` covers both Free and Mini Pass to **all four recurring tiers**, all recurring renewal boundaries, true paid same-cycle upgrades, accidental provider drift, and immediate cancellation.
The tests run against isolated test SQLite, **never live Neon**.

## Production audit / historical correction

When a previous first-purchase bug moved old usage into a newly bought subscription, compare verified purchase times to the reservation timestamps. Never globally zero a user's usage or change the Razorpay payment history. Correct only unambiguously misattributed reservations in a serializable, audited DB transaction. For the October 18, 2026 audited case, five sources (66.5223 minutes) were restored to the older verified Mini Pass period; the customer subscription remains provider-confirmed as immediately cancelled. This correction is logged as `billing.usage_period_repaired`.

Operational checks: compare the `/api/v1/usage` result with `usage`, `usage_reservations` and the applicable period key; check Razorpay's verified state before modifying entitlements. Production secrets must never appear in browser logs or source control.

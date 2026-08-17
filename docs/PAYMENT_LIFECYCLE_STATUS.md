# ClipKaro 7.8 — Live Payment Gate Status

**Evidence date:** 11 August 2026  
**Evidence SHA-256:** `9688f58cec5ac34a2d329fc5e0a17084d6f25c41d66f677d2053a03dee903214`

## Release decision

### ✅ PASSED — Live ₹59 Mini Pass payment lifecycle

The controlled Razorpay **live-mode** ₹59 Mini Pass transaction is accepted as release evidence for the one-time payment path. The evidence proves:

- live Razorpay credential authentication;
- ₹59 / 5,900-paise order creation;
- captured payment and provider order state `paid`;
- server-side checkout verification;
- entitlement transition `free → mini_pass`;
- 30-day Mini Pass validity;
- preserved usage counters;
- one local verified checkout / one entitlement activation; and
- focused billing lifecycle regression: **8 tests passed**.

Authoritative report: `docs/evidence/CLIPKARO_V7.8_LOCAL_PAYMENT_LIFECYCLE_REPORT.md`.

### ⏳ PENDING — Full recurring/production webhook lifecycle

The following are intentionally **not marked passed** because they were not completed in the evidence run:

- real Razorpay webhook delivery to the public production endpoint;
- real signed-webhook replay/idempotency;
- recurring mandate activation;
- a real monthly renewal charge;
- real cycle-end cancellation; and
- the complete flow behind production HTTPS/DNS/VPS.

Therefore the billing launch gate is currently **PARTIAL**: the ₹59 one-time Mini Pass path is **PASSED**, while the real recurring-subscription/webhook path remains **PENDING**.

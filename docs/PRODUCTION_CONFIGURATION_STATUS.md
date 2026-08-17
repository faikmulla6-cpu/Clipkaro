# Production configuration status — prepared 2026-08-11

**Paid-launch configuration status: BLOCKED (expected).**

A separate private VPS env draft was generated outside the source archive. The source tree contains no plaintext provider secrets.

Current blockers that still require real operator/provider input:

- ACME/TLS contact email
- provider credential rotation confirmation after plaintext exposure
- SMTP host and From address (plus auth pair if the provider requires authentication)
- legal operator/proprietor/entity name
- principal geographic address
- legal contact email
- privacy contact email
- customer-care email and phone
- grievance officer name, email and phone

The draft already has a newly generated application `SECRET_KEY` and a newly generated Razorpay webhook secret. Provider credentials supplied during migration are deliberately **not enough to enable paid launch** while `PRODUCTION_CREDENTIALS_ROTATED=false`.

After the missing values are filled and provider credentials are rotated:

```bash
python3.12 scripts/check-production-env.py --env-file .env --require-ready
docker compose --env-file .env -f docker-compose.hostinger.yml config --quiet
docker compose --env-file .env -f docker-compose.hostinger.yml up -d --build
```

Then verify the authenticated `/api/v1/system/preflight` response. Public paid traffic remains blocked unless `paid_launch_ready` is exactly `true`.

## Billing evidence already completed

The controlled **₹59 Mini Pass Razorpay live-mode payment lifecycle is PASSED** as of 11 August 2026. This proves the one-time checkout/capture/verification/entitlement path, but it does not remove the production configuration blockers above and it does not prove recurring webhook/renewal/cancellation behavior. See `docs/PAYMENT_LIFECYCLE_STATUS.md`.

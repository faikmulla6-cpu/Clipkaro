# Security and privacy

## Implemented

- Argon2id password hashing.
- Signed, expiring JWT in an HttpOnly, SameSite cookie; Secure in production mode.
- Double-submit CSRF protection on state-changing cookie-auth requests.
- Resource ownership enforced for projects, media, clips, exports, downloads, brand kits, and calendar items.
- Admin endpoint guarded by role.
- Upload type, extension, streamed size, readable-media, and plan duration validation.
- CORS allowlist, request IDs, rate limiting, `nosniff`, frame denial, referrer policy, and permissions policy.
- Razorpay HMAC verification and payment-event idempotency.
- Server-side Razorpay subscription creation; secret keys never enter the browser.
- Parameterized SQL and Pydantic validation.
- Audit events for account, upload, processing, export, and deletion events.
- Automatic source/export expiration cleanup.
- API errors avoid exposing file contents or another user's resource existence.

## Required before public launch

- Use a secrets manager and rotate the demo/production secrets.
- Add email verification, password reset, login lockout, breached-password screening, and session revocation.
- Scan uploads, isolate FFmpeg/Whisper workers, and set OS/container CPU, memory, disk, process, and time limits.
- Encrypt object storage, use short-lived signed URLs, and back up PostgreSQL.
- Add dependency/container scanning, a Content Security Policy, Sentry, structured logs, and alerting.
- Complete privacy, retention, consent, copyright, grievance, and takedown legal review for launch countries.

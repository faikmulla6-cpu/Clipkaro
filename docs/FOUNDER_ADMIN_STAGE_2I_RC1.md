# Stage 2I — Founder Admin RC1

This release-candidate branch freezes the promoted Founder Admin feature baseline for a final non-production rehearsal.

## Frozen source pair

- ClipKaro source baseline: `feature/founder-admin-api` at `b6264c76f8eaa705a4ae765dcd72eff5b380b788`
- ClipKaro RC branch: `feature/founder-admin-rc1`
- FounderConsole source baseline: `feature/admin-api-contract-integration` at `42d2a8669691fb343c2fbeecf43e9d8e85383012`
- FounderConsole RC branch: `release/founder-console-rc1`

## RC safety boundary

- Do not merge into ClipKaro `main`.
- Do not merge into `modal-no-vps` during Stage 2I.
- Do not modify `release/clipkaro-launch-v1.0.0`.
- Do not deploy Modal, Hostinger, Neon, B2, Razorpay, Resend, Groq, or any other provider.
- Do not install production credentials.
- `ADMIN_API_ENABLED=false` remains the production-template default.
- Founder Admin remains exactly nine GET-only routes with `fetch_one` / `fetch_all` database access.

## RC rehearsal

The Stage 2I workflow performs:

1. Python 3.11 and Python 3.12 compatibility checks.
2. Founder Admin security and production boot-gate tests.
3. Existing API and behavioral-learning regression tests.
4. AST verification of the nine GET-only routes and fetch-only database dependency.
5. A real Uvicorn server on `127.0.0.1` using temporary SQLite/local storage/local jobs only.
6. Invalid bearer-token rejection.
7. All nine Founder Admin requests through a FounderConsole-compatible request shape.
8. Exact `X-Request-ID` echo verification, `Cache-Control: no-store`, JSON response checks, and a 2 MiB response ceiling.
9. Sensitive-field exclusion and service-token non-echo verification.
10. `external_provider_probes=not_run` verification.
11. Before/after comparison of the seeded demo user's business state to prove the rehearsal does not mutate it.

Stage 2I is a release rehearsal only. It does not authorize production activation or any write action.

# ClipKaro Modal + Backblaze B2 No-VPS Deployment

## Locked topology

- `https://clipkaro.pro`: existing Hostinger Next.js frontend.
- Modal ASGI Function: existing FastAPI application; auth, sessions, quotas, billing, job creation and status only.
- Neon PostgreSQL: authoritative users, sessions, quotas, billing, upload sessions and durable job state.
- Backblaze B2 through the S3-compatible API: private source videos and exports.
- Modal media Function: one durable `JOB_ID` per invocation; ClamAV, FFmpeg, FFprobe, libass, ASR routing and export rendering.
- Resend, Razorpay, Groq, Cloudflare and the controlled ElevenLabs Hinglish Stage-1 remain unchanged.

There is no VPS, production SQLite database, public media bucket, permanent media worker, self-hosted AI model or durable dependency on container-local files.

## Provider adapters

The validated no-VPS branch already used cloud compatibility selectors `STORAGE_BACKEND=gcs` and `JOB_BACKEND=cloud_run_job`. On this branch those continue to mean "serverless cloud storage/job mode" while the concrete providers are selected independently:

```text
OBJECT_STORAGE_PROVIDER=s3
JOB_EXECUTION_PROVIDER=modal
```

This preserves the established local/GCP paths while moving production execution to Modal + S3-compatible storage without rewriting business logic.

## Modal secrets

Keep the existing Modal secret named `clipkaro-production` for the established production credentials. Post Karo uses a second narrowly scoped secret named `clipkaro-post-karo` containing only `POST_KARO_ENCRYPTION_KEY`. This separates social-publishing credential encryption from JWT/session signing and avoids modifying the existing production secret bundle.

Keep every value private. The existing `clipkaro-production` secret should ultimately contain:

- `DATABASE_URL` (Neon pooled TLS URL)
- `SECRET_KEY`
- `S3_ENDPOINT_URL`
- `S3_REGION`
- `S3_BUCKET_NAME`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `GROQ_API_KEYS`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `ELEVENLABS_API_KEYS` only for the existing controlled Stage-1 cohort
- `RESEND_API_KEY`
- `SOCIALKIT_ACCESS_KEY` when `YOUTUBE_INGESTION_PROVIDER=auto` or `socialkit`
- `EMAIL_FROM=ClipKaro AI <verify@clipkaro.pro>`
- public support aliases that are monitored before checkout goes live:
  `LEGAL_CONTACT_EMAIL=legal@clipkaro.pro`, `PRIVACY_CONTACT_EMAIL=privacy@clipkaro.pro`,
  `CUSTOMER_CARE_EMAIL=support@clipkaro.pro` and `GRIEVANCE_EMAIL=grievance@clipkaro.pro`
- Razorpay live key ID, key secret and webhook secret only after owner review
- the remaining public legal/customer-care launch particulars required by ClipKaro's paid-launch gate:
  operator name, principal address, customer-care phone, Grievance Officer name and grievance phone

Never put these values in Git, screenshots, logs or `NEXT_PUBLIC_*` variables.

### YouTube link ingestion

The creator-facing primary path is paste-a-YouTube-link. `YOUTUBE_INGESTION_PROVIDER=auto` keeps the bounded native yt-dlp path first and falls back to SocialKit only when native extraction is blocked. `YOUTUBE_INGESTION_PROVIDER=socialkit` uses the provider directly. ClipKaro sends a provider-side `max_duration` equal to the smaller of the plan source limit and the creator's remaining Karo Minutes, downloads only MP4 media from approved HTTPS provider/CDN hosts, scans it, stores it privately, and then continues through ClipKaro's existing ASR/ranking/export pipeline. Manual upload remains an optional fallback.

Do not enable `auto`/`socialkit` in production without `SOCIALKIT_ACCESS_KEY`; the production configuration gate fails closed. Keep the API key only in the Modal secret.

## Backblaze B2

Use a private bucket with server-side encryption enabled. Browser CORS must be restricted to `https://clipkaro.pro` for the S3-compatible API. ClipKaro stores only private object keys in PostgreSQL and issues short-lived SigV4 URLs for upload/download.

Expected key layout remains:

```text
quarantine/{user_id}/{upload_session_id}/{uuid}
users/{user_id}/projects/{project_id}/source/{uuid}
users/{user_id}/exports/{export_id}/clip.mp4
```

## Deploy Modal

Install the Modal CLI on a trusted development machine, authenticate to the correct workspace/environment, then from `backend/` run:

```text
modal deploy modal_app.py
```

`modal_app.py` deploys two independently autoscaling Functions in one App:

- `api`: lightweight FastAPI ASGI endpoint, concurrent I/O requests, no FFmpeg requirement.
- `run_media_job`: 2 CPU / 4 GiB initial media worker, 10 GiB ephemeral scratch, one job per input, one-hour timeout, scale-to-zero.

The media image installs FFmpeg, FFprobe, libass, fonts and ClamAV. Build is fail-closed if initial ClamAV signatures cannot be downloaded.

## Database migration

Before public traffic, run the existing Alembic baseline against the exact production Neon database from a trusted environment:

```text
cd backend
alembic upgrade head
```

Verify `alembic_version=20260817_01`. Do not auto-migrate on every API cold start.

## Hostinger

Keep:

```text
NEXT_PUBLIC_API_URL=/api/v1
```

Set the server-only `BACKEND_URL` to the generated Modal ASGI HTTPS URL. Keep the existing same-origin Next.js proxy. Until the frontend flag is generalized, retain `NEXT_PUBLIC_UPLOAD_MODE=direct_gcs`; on this branch the API returns an S3/B2 presigned URL behind the same direct-upload contract.

## Scale and cost controls

Initial deployment intentionally uses zero warm containers, API max 20 containers with per-container async concurrency, and media max 20 containers. Modal `.spawn()` provides a large pending-input queue while PostgreSQL remains the durable product authority. Increase media CPU/container limits only after measuring queue latency, render duration, memory and unit economics.

500 daily users do not imply 500 simultaneous renders. Product quotas must remain the primary cost guard. No infrastructure change may bypass Karo Minute/export reservations.

## Production gates

Do not claim production ready until all of these pass:

1. PostgreSQL migration/schema and cross-connection quota concurrency.
2. Real signup -> Resend verification -> logout/login.
3. B2 presigned browser upload from `https://clipkaro.pro` including CORS preflight.
4. Upload completion validates exact object size/content type/ownership.
5. One Modal media job: B2 download -> ClamAV -> FFprobe/ASR -> clip suggestions.
6. One real export for every frozen caption style regression set, with FFprobe/decode validation.
7. Signed private download.
8. Duplicate Modal invocation cannot double-charge or duplicate exports.
9. Razorpay webhook signature/idempotency and one explicitly authorized live checkout test.
10. Secret scan and no private media/database artifacts committed.

## Rollback

`main` remains unchanged and `cloudrun-no-vps` remains the preserved Google Cloud implementation. If Modal/B2 validation fails, stop using the Modal endpoint and return to the previous branch/runtime; do not force-push or rewrite production history.

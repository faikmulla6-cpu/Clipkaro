# ClipKaro No-VPS Deployment Guide

This guide prepares infrastructure manually after branch review. Commands use placeholders and never provision billing resources automatically.

## 1. Neon PostgreSQL

1. Create a Neon project and production branch manually.
2. Copy the pooled PostgreSQL connection URL into Secret Manager as `DATABASE_URL`; require TLS (`sslmode=require`).
3. Keep `POSTGRES_POOL_MIN_SIZE=0`, start with `POSTGRES_POOL_MAX_SIZE=4`, and use `POSTGRES_STATEMENT_CACHE_SIZE=0` with Neon's transaction-pooled URL.
4. From a trusted migration environment with the secret injected, run `cd backend` then `alembic upgrade head`.
5. Do not run migrations as the Cloud Run API startup command. Deploy only after the migration succeeds.

## 2. Google Cloud project and APIs

Create/select the project and enable manually: Cloud Run Admin API, Cloud Build or Artifact Registry APIs used by the chosen build path, IAM Credentials API, Secret Manager API, and Cloud Storage API. Attach billing only after owner review.

## 3. Private GCS bucket

Create one regional bucket near the Cloud Run region. Enable uniform bucket-level access and public-access prevention. Do not add `allUsers` or `allAuthenticatedUsers` bindings.

Apply a narrow CORS policy, replacing the example bucket name only:

```json
[
  {
    "origin": ["https://clipkaro.pro"],
    "method": ["PUT", "GET", "HEAD"],
    "responseHeader": ["Content-Type", "Content-Length", "ETag", "x-goog-generation"],
    "maxAgeSeconds": 900
  }
]
```

Recommended lifecycle rules delete `quarantine/` and `working/` objects after 1 day. Use application-owned exact-key deletion for projects/exports; lifecycle is defense in depth.

## 4. Service identities and secrets

Create separate API and media-job identities. Grant only the permissions listed in `NO_VPS_PRODUCTION_ARCHITECTURE.md`. If the runtime identity signs as itself, grant its principal `iam.serviceAccounts.signBlob` on only that service account and set `GCS_SIGNING_SERVICE_ACCOUNT` to its email. Do not download JSON keys.

Create Secret Manager entries (or equivalent Cloud Run secret references) for `SECRET_KEY`, `DATABASE_URL`, `GROQ_API_KEYS`, `CLOUDFLARE_API_TOKEN`, `ELEVENLABS_API_KEYS`, `RESEND_API_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`. Inject secrets as environment variables; the Python Secret Manager SDK is not needed.

## 5. Build images

From `backend/` build distinct targets:

```text
docker build --target api -t REGION-docker.pkg.dev/PROJECT/clipkaro/api:VERSION .
docker build --target media -t REGION-docker.pkg.dev/PROJECT/clipkaro/media:VERSION .
```

The API image excludes FFmpeg and model/alignment packages. The media image includes FFmpeg, FFprobe, libass, fonts, ClamAV, and the existing rendering assets.

## 6. Create the Cloud Run media job

Create one job with the media image, media identity, task count 1, retries appropriate to the idempotent claim (start at 1), and conservative parallelism. Configure all production backends and provider secrets. Set `CLAMAV_HOST=local` and `UPLOAD_SCAN_REQUIRED=true`. Do not set `JOB_ID` in the job template; the API supplies only this override per execution.

## 7. Deploy the FastAPI service

Deploy the API image with the API identity, public HTTPS ingress required by the Hostinger proxy, `PORT` supplied by Cloud Run, minimum instances 0, maximum instances 3, and concurrency 20 initially. Configure:

```text
APP_ENV=production
DATABASE_BACKEND=postgres
STORAGE_BACKEND=gcs
JOB_BACKEND=cloud_run_job
FRONTEND_URL=https://clipkaro.pro
APP_PUBLIC_URL=https://clipkaro.pro
CORS_ORIGINS=https://clipkaro.pro
GCP_PROJECT_ID=...
GCP_REGION=...
CLOUD_RUN_MEDIA_JOB_NAME=...
GCS_BUCKET=...
```

Run `python scripts/check-no-vps-production.py` in an equivalent injected environment before deployment. It prints status codes and booleans, never values.

## 8. Hostinger frontend

Keep `NEXT_PUBLIC_API_URL=/api/v1` and set `NEXT_PUBLIC_UPLOAD_MODE=direct_gcs`. Set the server-only `BACKEND_URL` to the Cloud Run HTTPS service URL. Never use a `NEXT_PUBLIC_*` variable for `BACKEND_URL` or any secret. Rebuild/restart the existing Hostinger Next.js application; do not move it to GCP.

## 9. Resend and Razorpay

Verify the ClipKaro sending domain manually, set an explicit `EMAIL_FROM`, and keep `FRONTEND_URL=https://clipkaro.pro`. Production rejects `onboarding@resend.dev`.

Configure Razorpay manually after review. The webhook URL is `https://clipkaro.pro/api/v1/billing/razorpay/webhook`. Keep signature validation and do not add browser CSRF to the webhook. No provider note grants entitlement.

## 10. Smoke test

After infrastructure exists, verify shallow API health, signup/login/logout and session revocation, email verification, direct upload initiation and GCS CORS, upload completion metadata checks, one full upload to ASR to edit to export to signed download, duplicate completion, duplicate job execution, quota concurrency, Mini Pass, subscription webhook ordering, and deletion/retention. Do not call production ready until live webhook, domain, payment, and complete media evidence exists.

## 11. Rollback

Keep the prior API image revision and frontend build available. Stop routing new traffic to the new API, restore the prior application revision, and restore PostgreSQL from a verified backup only if a data rollback is required. Never downgrade the baseline migration in place. GCS objects remain private during rollback. The `cloudrun-no-vps` branch must be reviewed and merged normally; never force-push production history.

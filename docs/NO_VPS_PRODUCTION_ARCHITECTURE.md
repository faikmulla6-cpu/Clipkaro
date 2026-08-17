# ClipKaro No-VPS Production Architecture

## Locked topology

The recommended production path is:

1. `https://clipkaro.pro` on Hostinger runs the Next.js frontend.
2. The same-origin Next.js `/api/*` rewrite uses the server-only `BACKEND_URL` to reach the FastAPI Cloud Run service.
3. FastAPI stores authoritative application, authentication, quota, billing, upload-session, and job state in PostgreSQL through `DATABASE_URL`. Neon is the initial provider; the SQL contract is standard PostgreSQL.
4. Browsers upload directly to a private GCS quarantine object through a short-lived V4 signed PUT URL.
5. FastAPI verifies GCS metadata, atomically creates project/video/job state, and starts a pre-created Cloud Run Job with only `JOB_ID` overridden.
6. The media job atomically claims the job, downloads bounded scratch input, scans and validates it, uses the existing Groq to Cloudflare routing (or controlled ElevenLabs Hinglish Stage-1), executes the existing FFmpeg/FFprobe/ASS renderer, writes private GCS output, and exits.
7. Authenticated downloads redirect to short-lived signed GCS GET URLs. No object is public.

There is no required VPS, permanent worker, production SQLite database, durable container filesystem, self-hosted model server, Redis, or paid third-party renderer.

## Runtime modes

| Concern | Local development | Production |
|---|---|---|
| Database | `DATABASE_BACKEND=sqlite` | `DATABASE_BACKEND=postgres` |
| Storage | `STORAGE_BACKEND=local` | `STORAGE_BACKEND=gcs` |
| Jobs | `JOB_BACKEND=local` | `JOB_BACKEND=cloud_run_job` |
| Upload | FastAPI multipart | signed direct GCS PUT |
| Media execution | background/local worker | one Cloud Run Job execution |

Production startup fails when any legacy backend is selected. PostgreSQL schema changes are performed only by Alembic; API startup checks revision `20260817_01` and never auto-migrates.

## Concurrency and financial safety

PostgreSQL row locks, unique constraints, conditional updates, and triggers are authoritative for Karo Minute/export reservations. Reservations are unique per resource and settle once. Razorpay checkout creation retains the process lock as an optimization and uses a PostgreSQL advisory lock across API instances. Provider references and webhook event IDs remain unique. Terminal event and ordering state remains durable.

Cloud Run executions claim one specific queued `JOB_ID`. A duplicate/retried execution cannot claim a processing or completed job. Claims persist attempt, start, heartbeat, failure, completion, and execution metadata. `python -m app.reconcile_jobs` can later be scheduled to requeue only stale claims.

## Private media and object keys

Database rows store object keys and optional generations, never public URLs:

- `quarantine/{user_id}/{upload_session_id}/{uuid}`
- `users/{user_id}/projects/{project_id}/source/{uuid}`
- `users/{user_id}/exports/{export_id}/clip.mp4`

Every read/delete validates a server-generated ownership prefix. Completion verifies session ownership, expiry, exact key, object existence, size, content type, and generation before consuming the session. Repeated completion is idempotent.

## Frozen product behavior

The migration does not modify caption style data or ASR routing. Kinetic, Clean, Bold, Minimal, and India Pop continue through the existing FFmpeg/FFprobe/ASS/libass renderer. Default routing remains Groq then Cloudflare. Controlled Hinglish Stage-1 remains ElevenLabs then the established legacy fallback. Roman V3, Display V1, provider timestamps, and fallback/latency observability remain unchanged.

## Identities and permissions

Use separate service identities when practical.

API identity:

- read object metadata for completion;
- create signed upload/download requests (the signing identity needs `iam.serviceAccounts.signBlob`, normally through `roles/iam.serviceAccountTokenCreator` on only that identity);
- invoke only the configured media job (`run.jobs.run`, typically a narrow custom role or `roles/run.invoker` plus the exact Jobs run permission as required by the current API);
- read only required Secret Manager secret versions if secrets are not injected by deployment tooling.

Media identity:

- read/delete quarantine and source objects and create export/source objects in only the ClipKaro bucket;
- connect to Neon using the injected `DATABASE_URL`;
- access only required provider secrets.

No downloadable service-account JSON is required or permitted.

## Cost controls

Start conservatively: API minimum instances `0`, maximum instances `3`, concurrency `20`; media job parallelism `1-2`, one task per execution, 2-4 vCPU, 4-8 GiB memory, and a 30-60 minute timeout based on measured 1080p renders. Keep PostgreSQL pool maximum at `4` per API/job instance and media job task count at one. Increase only with measured queue, connection, memory, and render evidence.

## Retention and observability

Apply GCS lifecycle deletion to quarantine objects after 1 day and temporary/working objects after 1-2 days; retain exports according to the product policy. Database cleanup deletes known exact keys before marking rows expired. Recommended structured identifiers are request, upload session, project, job, export, provider, stage, attempt, latency, and result category. Never log secrets, signed URLs, tokens, database URLs, or full private transcripts.

Legacy `docker-compose.hostinger.yml` and VPS documentation remain for historical/local compatibility only. They are not the production recommendation.

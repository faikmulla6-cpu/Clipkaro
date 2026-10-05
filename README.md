# ClipKaro AI — No-VPS Serverless Production Candidate v7.8

Selecting Hindi now means spoken Hindi/Hinglish rendered in readable Latin script (`main kaise hoon… arre yaar, haan sahi mein`). Recognition remains in the acoustic model's native script for verification and alignment; transliteration happens only in the display layer.

The recommended production architecture keeps the Next.js frontend on Hostinger and runs FastAPI on Cloud Run, PostgreSQL on Neon, private media in GCS, and the existing renderer in Cloud Run Jobs. See `docs/NO_VPS_PRODUCTION_ARCHITECTURE.md` and `docs/NO_VPS_DEPLOYMENT_GUIDE.md`. Legacy VPS files remain optional compatibility artifacts.

ClipKaro AI is an India-first creator product that turns owned long-form videos into ranked, editable, platform-ready Shorts. This edition is a real full-stack product rather than a static prototype: accounts, uploads, AI jobs, live progress, project ownership, clip editing, FFmpeg rendering, downloads, analytics, brand kits, templates, calendar drafts, billing webhooks, admin health, expiry cleanup, and tests are connected.

## Product flow

1. Create an account, verify email ownership, and sign in. Local QA may explicitly seed a private test account, but demo credentials are disabled by default.
2. Upload an MP4, MOV, WebM, or MKV you own.
3. Watch real pipeline stages through Server-Sent Events: validation, audio, transcription, ranking, and previews.
4. Review AI moments with hook/clarity/value/emotion/flow scores and reasons.
5. Edit the hook and title in Creator Studio; choose caption style and 9:16, 4:5, or 1:1 output.
6. Render 720p or 1080p H.264/AAC with burned captions, hook text, brand styling, and plan-aware watermarking.
7. Watch live export progress, download the MP4, and optionally add it to the content calendar.

## Launch features

- Argon2 password hashing, signed HttpOnly sessions, per-resource ownership, role-protected admin endpoint.
- Streaming upload validation and plan-aware file-size/source-duration enforcement.
- API-first speech recognition with Groq primary + Cloudflare fallback for the legacy route, provider-native word timestamps, durable provider-attempt/latency observability, and an explicitly gated ElevenLabs Roman-Hinglish cohort route. Legacy local faster-whisper/WhisperX remains qualification-only.
- Explainable clip ranking with non-overlapping 20–90 second candidates.
- Real-time SSE updates backed by persistent job records.
- Browser studio with hook/title editing, caption personalities, aspect ratios, quality, and watermark controls.
- Real FFmpeg/ASS renderer with audio-locked active-word captions, accurate seeking, Unicode Windows fonts, validated mobile-safe MP4, branding, and automatic expiry.
- India Pop, Clean Educator, Podcast Punch, Business Edge, Minimal Story, and Spiritual Calm templates.
- Creator brand kits and a rights-safe scheduling draft calendar.
- Fair Access usage ledger: Free ₹0, Mini Pass ₹59 one-time, Creator ₹199, Growth ₹399, Pro ₹799, Agency ₹1,999.
- Enforced Karo Minutes and Short export quotas per entitlement period; every paid tier gets 1080p and no watermark.
- Razorpay Standard Checkout with server-side signature verification, provider-side capture confirmation for one-time purchases, automatic live Plan creation/reuse, recurring subscriptions, cycle-end cancellation, renewal/status synchronization, signed webhook idempotency, and webhook recovery for captured Mini Pass payments.
- Rate limiting, security headers, request IDs, audit records, cleanup worker, API docs, Docker, and tests.


## Locked Fair Access pricing

| Plan | Price | Karo Minutes | Shorts | Quality |
| --- | ---: | ---: | ---: | --- |
| Free | ₹0 | 15/month | 2/month | 720p + watermark |
| Mini Pass | ₹59 one-time | 125 total (25 max per Short) | 5 | 1080p, no watermark |
| Creator | ₹199/month | 60 | 15 | 1080p, no watermark |
| Growth | ₹399/month | 180 | 50 | 1080p, no watermark |
| Pro | ₹799/month | 480 | 150 | 1080p, no watermark |
| Agency | ₹1,999/month | 1,500 | 500 | 1080p, no watermark |

`1 Karo Minute = 1 source-video minute processed.` Mini Pass includes 5 Short credits with up to 25 source-processing minutes per Short, capped at 125 source minutes across the pass. The backend enforces both processing minutes and export limits. Razorpay plan IDs are created or reused automatically on first checkout, so there are no manual `RAZORPAY_PLAN_*` IDs to maintain.

The delivered private `backend/.env` contains the configured Razorpay server credentials. Never commit that file. The public key ID may be used by the browser; the key secret must remain backend-only. See `docs/RAZORPAY_BILLING.md`.

## Fastest Windows setup

Install these first:

- Node.js 20 or newer
- Python 3.11 or newer
- FFmpeg added to `PATH`

Then open PowerShell in the project folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-windows.ps1
```

Open <http://localhost:3000>. Demo-user seeding is **off by default**. For local QA, create a normal account through signup or explicitly seed a private test account without committing credentials.

## Manual setup

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend in a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The default configuration is API-first (`ASR_MODE=api`) and does not download a local Whisper model. The optional qualification/local profile can still use faster-whisper/WhisperX when explicitly selected. If transcript verification/timing safety fails, ClipKaro deliberately creates no clips.

## Docker launch

```bash
docker compose up --build
```

Visit the web app at <http://localhost:3000> and API documentation at <http://localhost:8000/docs>.

## Verification

```bash
cd backend && pytest -q
cd ../frontend && npm run build
```

The test suite covers scoring, subtitle timing, authentication, usage, upload persistence, manual transcript analysis, edit/export queueing, and cross-account ownership isolation. `scripts/verify.sh` runs the main checks on macOS/Linux.

## Production configuration

### Before public paid launch

The repository is deliberately domain-neutral. Configure the purchased HTTPS domain, real operator/customer-care/grievance particulars, a verified Resend sender (or SMTP fallback), rotated provider credentials, and the Razorpay LIVE webhook secret only in the private production environment. The generic `.env.production.example` fails closed and does not enable the private Hinglish cohort by default.


API-first ASR migration details and provider configuration are in
[`docs/API_FIRST_ASR.md`](docs/API_FIRST_ASR.md). API mode is implemented but
is not Hindi/Marathi/Hinglish quality-certified until the frozen real-ASR
qualification contract passes.

The authenticated `/api/v1/system/preflight` endpoint now separates **processing readiness** (`ready`) from **paid-launch readiness** (`paid_launch_ready`). It performs secret-safe health checks for persistent storage, FFmpeg/FFprobe, ClamAV, worker heartbeat, worker/API-ASR capability, Resend transactional-email configuration, read-only Razorpay authentication, legal operator particulars, and worker-side provider status. Provider responses, hostnames, credentials and secret values are never returned.

Before public traffic:

1. Set `APP_ENV=production`, a long random `SECRET_KEY`, strict `CORS_ORIGINS`, and `SEED_DEMO_USER=false`.
2. Use `docker-compose.hostinger.yml`: production defaults to `ASR_MODE=api`, with provider-native word timestamps and `ALIGNMENT_BACKEND=native`. The optional local/qualification path can still use faster-whisper/WhisperX, but the production API-ASR worker does not require that heavyweight runtime.
3. Put the frontend/API behind HTTPS and a reverse proxy that does not buffer SSE.
4. Configure `RAZORPAY_WEBHOOK_SECRET`; point Razorpay to `/api/v1/billing/razorpay/webhook`.
5. Mount durable storage or switch media to R2/S3. Keep the expiry cleanup worker active.
6. Move the persistent job contract to Celery/Dramatiq + Redis before horizontal scaling.
7. Replace SQLite with PostgreSQL before multiple API replicas.
8. Configure off-host backups/monitoring and verify alerting. Malware scanning and transactional-email code are already integrated; production still needs live ClamAV readiness and a verified Resend sender (or SMTP fallback).
9. Publish the real Terms, Privacy Policy, rights attestation, takedown process, operator/customer-care/grievance particulars, and support contacts.

See:

- `docs/ARCHITECTURE.md` — system design and scale path
- `docs/PRODUCT_STRATEGY.md` — competitor-informed product decisions
- `docs/LAUNCH_PLAYBOOK.md` — launch checklist, metrics, and operations
- `docs/LAUNCH_READINESS_7_8_0.md` — launch-candidate status, external prerequisites, backup/verification gates
- `docs/SECURITY.md` — implemented controls and production hardening
- `docs/PRODUCTION_SECRETS_AND_LEGAL.md` — private VPS secrets, rotation and public operator particulars
- `docs/QA_REPORT.md` — verification evidence and dependency advisory
- `docs/SELF_HOSTED_RUNNER.md` — zero-GitHub-minute Linux runner requirements, registration and security boundary
- `docs/DELIVERY_PLAN.md` — milestone/issue plan

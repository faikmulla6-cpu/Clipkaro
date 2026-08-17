# ClipKaro AI v7.7 — Hostinger Production Release

## What changed

- Primary ASR remains `medium`; independent verification now defaults to `small`
  instead of `turbo`, reducing CPU and memory pressure.
- The second full-video pass runs only when consensus is enabled.
- Primary and recovery beam sizes were reduced conservatively; hallucination,
  speech-coverage, repetition, timing, and WER gates remain active.
- CPU threads, ASR workers, and FFmpeg concurrency are explicitly bounded.
- Interrupted upload analysis resumes after an API/container restart. Interrupted
  exports fail clearly and can be retried instead of staying frozen.
- The Hostinger Compose stack provides Caddy HTTPS, same-origin `/api` routing,
  health checks, persistent database/media/model volumes, and restart policies.
- Backend Docker builds no longer depend on a missing local `storage` directory.

## Hostinger VPS deployment

1. Point the domain `A` record to the VPS IP.
2. On the VPS, install Docker Engine and the Docker Compose plugin, then clone
   the GitHub repository: `git clone https://github.com/faikmulla/ClipkaroAI.git`.
3. Copy `.env.production.example` to `.env` and replace `DOMAIN`, `ACME_EMAIL`,
   and `SECRET_KEY`. Add the live Razorpay values only in this VPS `.env` file.
4. Run `docker compose -f docker-compose.hostinger.yml up -d --build`.
5. Run `docker compose -f docker-compose.hostinger.yml logs -f` until API and
   web health checks pass and Caddy issues the certificate.

For updates, run `git pull --ff-only` followed by
`docker compose -f docker-compose.hostinger.yml up -d --build`. The Docker
volume named `clipkaro_storage` contains the SQLite database, uploads, exports,
and downloaded models; do not remove it during a normal release.

Do not use shared web hosting: local FFmpeg and Whisper processing require a VPS.
Use at least 4 vCPU and 8 GB RAM for the default medium+small accuracy profile.
For a smaller server, use `WHISPER_MODEL=small`, but accuracy will decrease.

## Verified

- Backend: 41 tests passed.
- Python compile: passed.
- Real FFmpeg render: H.264 720×1280 + AAC, 3.0 seconds, passed output validation.
- Frontend source was inspected, but a clean Next build could not run because the
  current npm mirror returned incomplete/corrupted packages (`next` executable absent).

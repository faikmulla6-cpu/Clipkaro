# ClipKaro Stage 2J — Codex Final Validation Handoff

This archive is the **pre-push Stage 2J candidate** for `feature/founder-admin-activation-prep`.
It is intentionally **not activated**: Founder Admin remains fail-closed and no production secret is included.

## Non-negotiable safety boundary

- Do **not** merge to `main` or `modal-no-vps` during validation.
- Do **not** deploy or change DNS.
- Keep `ADMIN_API_ENABLED=false` until the separately approved production activation step.
- Do not create, print, commit, or expose a real `ADMIN_API_SERVICE_TOKEN` during validation.
- Do not weaken, skip, mark optional, or remove a failing release/security test just to obtain green CI.
- Do not commit generated files (`node_modules`, `.next`, `*.tsbuildinfo`, `.venv*`, pytest caches, audit/JUnit/launch evidence).

## Expected validation environment

Use a Linux/Ubuntu environment matching GitHub Actions as closely as practical:

- Python 3.12
- Node.js 20+ (CI uses Node 20; production frontend image uses Node 24)
- FFmpeg + FFprobe
- Docker Engine + Docker Compose plugin
- Git

## 1. Establish a clean Git worktree

Unzip the archive into a new directory, initialize/attach it to the intended repository, and verify the branch target is:

```text
feature/founder-admin-activation-prep
```

Before tests, record:

```bash
git status --short
git diff --check
```

There should be no unrelated local files or secrets.

## 2. Static + Stage 2J fail-closed verification

From repository root:

```bash
python scripts/verify-release-static.py
python backend/scripts/verify_stage2j_activation_prep.py
```

Expected current source result before dependency/runtime testing:

```text
Static release verification: 137 passed, 0 failed
Stage 2J Founder Admin activation preparation: PASS
```

## 3. Backend dependencies and full tests

```bash
cd backend
python -m venv .venv-codex
source .venv-codex/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m pip check
APP_ENV=test TRANSCRIPTION_BACKEND=fixture PYTHONPATH=. pytest -q
cd ..
```

Do not hide skips/failures. Investigate any failure before pushing.

## 4. Frontend install, contracts, audit, typecheck and production build

Use the committed lockfile exactly:

```bash
cd frontend
npm ci --no-audit --no-fund
npm run check:release
npm run typecheck
npm audit --omit=dev --audit-level=high
BACKEND_URL=https://clipkaro-ci-backend.invalid npm run build
cd ..
```

Important:

- Prefer `npm ci`, not `npm install`.
- Do not regenerate `package-lock.json` merely because a different npm version formats optional metadata differently.
- If `npm audit` finds a high/critical production advisory, fix it without broad major-version upgrades unless required and rerun every frontend gate.
- After `next build`, `frontend/next-env.d.ts` must remain unchanged and no `frontend/tsconfig.tsbuildinfo` may become tracked.

## 5. Production configuration and image validation

Use harmless CI placeholders only:

```bash
DOMAIN=clipkaro.example \
ACME_EMAIL=ci@example.com \
SECRET_KEY=ci-only-secret-key-with-at-least-32-characters \
docker compose -f docker-compose.hostinger.yml config --quiet
```

Build the actual production targets used by the API-first architecture:

```bash
docker build --pull --target api -t clipkaro-api:codex backend
docker build --pull --target media -t clipkaro-media:codex backend
docker build --pull \
  --build-arg BACKEND_URL=https://clipkaro-ci-backend.invalid \
  -t clipkaro-frontend:codex frontend
```

Validate the lightweight production media runtime:

```bash
docker run --rm --entrypoint python clipkaro-media:codex -c \
"import importlib.util, shutil; required=('ffmpeg','ffprobe','tesseract','clamscan'); missing=[x for x in required if not shutil.which(x)]; assert not missing, missing; assert importlib.util.find_spec('faster_whisper') is None; assert importlib.util.find_spec('whisperx') is None; import app.media_job; print('production media runtime validated')"
```

The heavyweight `worker` target is reserved for explicitly selected local WhisperX qualification/deployment and is **not** the default Fresh Launch image.

## 6. Final source-hygiene check

Clean only generated validation artifacts, then verify source has not been changed by tests/builds:

```bash
rm -rf backend/.venv-codex backend/.pytest_cache backend/**/__pycache__
rm -rf frontend/node_modules frontend/.next
rm -f backend/pytest-report.xml frontend/npm-audit-production.json
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete

git diff --check
git status --short
python scripts/verify-release-static.py
python backend/scripts/verify_stage2j_activation_prep.py
```

Only intentional Stage 2J finalization changes should remain.

## 7. Push boundary

After **all** local checks are green, commit/push only to:

```text
feature/founder-admin-activation-prep
```

Then let GitHub run the authoritative Ubuntu gates on the exact pushed SHA:

- ClipKaro CI
- Critical Product Contracts
- Fresh Launch QA
- Founder Admin Stage 2J Activation Prep / Cloud Gate as applicable

Do not activate Founder Console or the ClipKaro Admin API merely because the push is green. Production activation remains a separate explicit GO step.

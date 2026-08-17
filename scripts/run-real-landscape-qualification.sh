#!/usr/bin/env bash
set -uo pipefail

export TERM="${TERM:-dumb}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
EVIDENCE="$BACKEND/landscape-qualification-evidence"
OUTPUT="$BACKEND/landscape_qa"
SOURCE_DIR="${LANDSCAPE_SOURCE_DIR:-}"

export APP_ENV=development
export TRANSCRIPTION_BACKEND=fixture
export MEDIA_FFMPEG_THREADS="${MEDIA_FFMPEG_THREADS:-2}"
export MEDIA_PROCESS_TIMEOUT_SECONDS="${MEDIA_PROCESS_TIMEOUT_SECONDS:-300}"
export PYTHONPATH=.

rm -rf "$OUTPUT" "$EVIDENCE"
rm -f "$BACKEND/landscape-execution-preflight.json" "$BACKEND/landscape-runner-hardware.txt" "$BACKEND/landscape-qa-resource.txt"
mkdir -p "$EVIDENCE"

finish_evidence() {
  cd "$BACKEND" || return
  python scripts/write_landscape_threshold_lock.py \
    --phase after \
    --output landscape-qualification-evidence/threshold-lock-after.json >/dev/null 2>&1 || true
  python scripts/finalize_landscape_qualification.py \
    --evidence-dir landscape-qualification-evidence || true
}
trap finish_evidence EXIT

cd "$BACKEND"
python scripts/write_landscape_threshold_lock.py \
  --phase before \
  --output landscape-qualification-evidence/threshold-lock-before.json

{
  echo "qualification_attempt_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "tested_sha=${TESTED_SHA:-unset}"
  uname -a
  lscpu 2>/dev/null || true
  free -h 2>/dev/null || true
  df -h "$ROOT" 2>/dev/null || true
  ffmpeg -version 2>/dev/null | head -n 3 || true
  ffprobe -version 2>/dev/null | head -n 2 || true
  python --version 2>&1 || true
  python - <<'PY' 2>/dev/null || true
try:
    import cv2
    print("opencv=" + cv2.__version__)
except Exception as exc:
    print("opencv_unavailable=" + type(exc).__name__)
PY
} > landscape-runner-hardware.txt

preflight_args=(--output landscape-execution-preflight.json)
if [[ -n "$SOURCE_DIR" ]]; then
  preflight_args+=(--source-dir "$SOURCE_DIR")
fi
python scripts/check_landscape_execution_environment.py "${preflight_args[@]}"
preflight=$?

if ! git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
  echo "ERROR: exact-candidate landscape qualification requires a Git checkout, not an extracted ZIP." >&2
  exit 3
fi
export TESTED_SHA="${TESTED_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$TESTED_SHA" ]] || {
  echo "ERROR: HEAD does not match TESTED_SHA." >&2
  exit 3
}
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]] || {
  echo "ERROR: tracked working tree is dirty." >&2
  exit 3
}
if [[ "$preflight" -ne 0 ]]; then
  exit "$preflight"
fi

cmd=(
  python scripts/landscape_export_qa.py
  --output-dir landscape_qa
  --cases 10
  --clip-seconds 8
  --samples 12
)
if [[ -n "$SOURCE_DIR" ]]; then
  cmd+=(--source-dir "$SOURCE_DIR")
fi

set +e
/usr/bin/time -v -o landscape-qa-resource.txt "${cmd[@]}"
raw=$?
set -e

python scripts/write_landscape_threshold_lock.py \
  --phase after \
  --output landscape-qualification-evidence/threshold-lock-after.json
trap - EXIT
python scripts/finalize_landscape_qualification.py \
  --evidence-dir landscape-qualification-evidence \
  --enforce
final=$?
echo "raw_landscape_exit=$raw final_qualification_exit=$final"
exit "$final"

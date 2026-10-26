#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
EVIDENCE="$BACKEND/asr-qualification-evidence"
PRIMARY_MODEL="${WHISPER_MODEL:-medium}"
CASES_PER_LANGUAGE="${CASES_PER_LANGUAGE:-3}"
MIN_CASE_SECONDS="${MIN_CASE_SECONDS:-40}"

export APP_ENV=development
export TRANSCRIPTION_BACKEND=faster-whisper
export WHISPER_MODEL="$PRIMARY_MODEL"
export WHISPER_SECONDARY_MODEL="${WHISPER_SECONDARY_MODEL:-small}"
export REQUIRE_ASR_CONSENSUS=true
export ALIGNMENT_BACKEND=whisperx
export REQUIRE_FORCED_ALIGNMENT=true
export AUTO_LANGUAGE_BIAS=india
export HINDI_CAPTION_SCRIPT=roman
export ASR_CONCURRENCY=1
export ASR_CPU_THREADS="${ASR_CPU_THREADS:-4}"
export ASR_WORKERS=1
export MEDIA_FFMPEG_THREADS="${MEDIA_FFMPEG_THREADS:-2}"
export PYTHONPATH=.

mkdir -p "$EVIDENCE"

finish_evidence() {
  cd "$BACKEND" || return
  python scripts/write_asr_threshold_lock.py --phase after --output asr-qualification-evidence/threshold-lock-after.json >/dev/null 2>&1 || true
  python scripts/finalize_asr_qualification.py --evidence-dir asr-qualification-evidence || true
}
trap finish_evidence EXIT

cd "$ROOT"
python3 backend/scripts/write_asr_threshold_lock.py --phase before --output backend/asr-qualification-evidence/threshold-lock-before.json
{
  echo "qualification_attempt_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  uname -a
  lscpu 2>/dev/null || true
  free -h 2>/dev/null || true
  df -h "$ROOT" 2>/dev/null || true
  ffmpeg -version 2>/dev/null | head -n 3 || true
  python3 --version 2>&1 || true
} > backend/asr-runner-hardware.txt
if ! git rev-parse HEAD >/dev/null 2>&1; then
  echo "ERROR: exact-main qualification requires a Git checkout, not an unversioned extracted ZIP." >&2
  python3 backend/scripts/check_asr_execution_environment.py --check-runtime --output backend/asr-execution-preflight.json || true
  exit 3
fi
export TESTED_SHA="${TESTED_SHA:-$(git rev-parse HEAD)}"
[[ "$(git rev-parse HEAD)" == "$TESTED_SHA" ]] || { echo "ERROR: HEAD does not match TESTED_SHA." >&2; exit 3; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo "ERROR: tracked working tree is dirty." >&2; exit 3; }

cd "$BACKEND"
python3 scripts/check_asr_execution_environment.py --output asr-execution-preflight.json || true
cd "$ROOT"
if [[ "${RUNNER_ENVIRONMENT:-}" == "github-hosted" ]]; then
  bash scripts/check-github-hosted-runner.sh --profile asr
else
  bash scripts/check-self-hosted-runner.sh --profile asr
fi

cd "$BACKEND"
rm -rf .venv-ci
python3.12 -m venv .venv-ci
# shellcheck disable=SC1091
source .venv-ci/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -r requirements-alignment.txt
pip install "fsspec[http]==2026.7.0" pyarrow==25.0.0
python -m pip check
python scripts/check_asr_execution_environment.py --check-runtime --output asr-execution-preflight.json
python -c "from app.services.forced_alignment import validate_forced_alignment_runtime; print(validate_forced_alignment_runtime('whisperx', True, enforce_production_policy=True, enforce_pinned_versions=True))"

{
  echo "tested_sha=$TESTED_SHA"
  echo "primary_model=$PRIMARY_MODEL"
  echo "cases_per_language=$CASES_PER_LANGUAGE"
  echo "min_case_seconds=$MIN_CASE_SECONDS"
  uname -a
  lscpu
  free -h
  ffmpeg -version | head -n 3
  python --version
  python - <<'PY'
import importlib.metadata as metadata
for package in ("faster-whisper", "whisperx", "torch", "torchaudio", "torchvision"):
    print(f"{package}={metadata.version(package)}")
PY
} > asr-runner-hardware.txt

python scripts/fetch_fleurs_stress_corpus.py --output-dir stress_corpus --cases-per-language "$CASES_PER_LANGUAGE" --min-seconds "$MIN_CASE_SECONDS"
python scripts/import_mucs_hinglish_corpus.py --output-dir stress_corpus --cases "$CASES_PER_LANGUAGE" --min-seconds "$MIN_CASE_SECONDS"
python scripts/fetch_public_asr_noise_pack.py --output-dir stress_corpus/noise

set +e
/usr/bin/time -v -o asr-core-resource.txt python scripts/asr_stress_benchmark.py --manifest stress_corpus/manifest.json --street-noise stress_corpus/noise/traffic.ogg --model "$PRIMARY_MODEL" --mode qualification --min-cases-per-language "$CASES_PER_LANGUAGE" --output asr-stress-report.json
core=$?
for noise in cafe fan; do
  /usr/bin/time -v -o "asr-${noise}-resource.txt" python scripts/asr_stress_benchmark.py --manifest stress_corpus/manifest.json --street-noise "stress_corpus/noise/${noise}.ogg" --model "$PRIMARY_MODEL" --mode smoke --scenarios street_noise --min-cases-per-language "$CASES_PER_LANGUAGE" --output "asr-${noise}-report.json"
  eval "${noise}=\$?"
done
python - <<'PY'
import json
from pathlib import Path
p=Path("stress_corpus/manifest.json")
payload=json.loads(p.read_text(encoding="utf-8"))
for row in payload["cases"]:
    language=str(row.get("language") or "").lower()
    row["language_hint"]="hi" if language=="hi" else "mr" if language=="mr" else "hinglish"
Path("stress_corpus/manifest-hinted.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
PY
/usr/bin/time -v -o asr-hinted-resource.txt python scripts/asr_stress_benchmark.py --manifest stress_corpus/manifest-hinted.json --street-noise stress_corpus/noise/traffic.ogg --model "$PRIMARY_MODEL" --mode smoke --scenarios clean,street_noise --min-cases-per-language "$CASES_PER_LANGUAGE" --output asr-hinted-report.json
hinted=$?
/usr/bin/time -v -o asr-concurrency-resource.txt python scripts/asr_concurrency_soak.py --manifest stress_corpus/manifest.json --model "$PRIMARY_MODEL" --output asr-concurrency-report.json
concurrency=$?
set -e

python scripts/write_asr_threshold_lock.py --phase after --output asr-qualification-evidence/threshold-lock-after.json
trap - EXIT
python scripts/finalize_asr_qualification.py --evidence-dir asr-qualification-evidence --enforce
final=$?
echo "raw_stage_exit_codes core=$core cafe=$cafe fan=$fan hinted=$hinted concurrency=$concurrency final=$final"
exit "$final"

#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-all}"
if [[ "$PROFILE" == "--profile" ]]; then
  PROFILE="${2:-all}"
fi

fail() { echo "[runner-check] ERROR: $*" >&2; exit 1; }
warn() { echo "[runner-check] WARNING: $*" >&2; }
ok() { echo "[runner-check] OK: $*"; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' is missing."; }
version_major() {
  "$@" 2>/dev/null | head -n1 | grep -oE '[0-9]+' | head -n1 || true
}

[[ "$(uname -s)" == "Linux" ]] || fail "Runner must be Linux; found $(uname -s)."
case "$(uname -m)" in
  x86_64|amd64) ;;
  *) fail "Runner must be x64; found $(uname -m)." ;;
esac
[[ "$(id -u)" -ne 0 ]] || fail "Do not run the GitHub runner service as root. Use a dedicated unprivileged account."
ok "Linux x64 non-root runner user $(id -un)"

need_cmd bash
need_cmd git
need_cmd python3.12
PY_MAJOR_MINOR="$(python3.12 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
[[ "$PY_MAJOR_MINOR" == "3.12" ]] || fail "Python 3.12 is required; found $PY_MAJOR_MINOR."
python3.12 -m venv --help >/dev/null 2>&1 || fail "Python venv support is missing (install python3.12-venv)."
ok "Python $PY_MAJOR_MINOR with venv"

case "$PROFILE" in
  governance)
    ;;
  ci-backend|critical-backend)
    need_cmd ffmpeg
    need_cmd ffprobe
    ffmpeg -version >/dev/null 2>&1 || fail "ffmpeg is installed but not executable."
    ;;
  ci-frontend|critical-frontend)
    need_cmd node
    need_cmd npm
    NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
    [[ "$NODE_MAJOR" == "20" ]] || fail "Node.js 20 is required; found $(node --version)."
    need_cmd docker
    docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable to the runner user."
    docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 plugin is required."
    ;;
  landscape)
    need_cmd ffmpeg
    need_cmd ffprobe
    [[ -x /usr/bin/time ]] || fail "GNU /usr/bin/time is required."
    ;;
  asr)
    need_cmd ffmpeg
    need_cmd ffprobe
    need_cmd curl
    [[ -x /usr/bin/time ]] || fail "GNU /usr/bin/time is required."
    ;;
  launch|all)
    need_cmd ffmpeg
    need_cmd ffprobe
    need_cmd node
    need_cmd npm
    NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
    [[ "$NODE_MAJOR" == "20" ]] || fail "Node.js 20 is required; found $(node --version)."
    need_cmd docker
    docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable to the runner user."
    docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 plugin is required."
    [[ -x /usr/bin/time ]] || fail "GNU /usr/bin/time is required."
    ;;
  *) fail "Unknown profile '$PROFILE'." ;;
esac

# Heavy launch qualification needs enough local headroom for Docker layers,
# Whisper/WhisperX caches and real-media artifacts. Keep the hard floor modest
# enough for CI; report a warning below the recommended production-class size.
if [[ "$PROFILE" == "asr" || "$PROFILE" == "launch" || "$PROFILE" == "all" ]]; then
  MEM_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
  MEM_MIB=$(( MEM_KB / 1024 ))
  MEM_GIB=$(( MEM_KB / 1024 / 1024 ))
  # A marketed 8 GB host normally exposes roughly 7.4-7.8 GiB after firmware/kernel reservations.
  (( MEM_MIB >= 7400 )) || fail "Heavy QA requires an 8 GB-class host (>=7400 MiB visible RAM); detected ${MEM_MIB} MiB."
  (( MEM_MIB >= 11264 )) || warn "12+ GiB visible RAM is recommended for production-class WhisperX qualification; detected ${MEM_MIB} MiB."

  FREE_KB="$(df -Pk "${RUNNER_TEMP:-/tmp}" | awk 'NR==2 {print $4}')"
  FREE_GIB=$(( FREE_KB / 1024 / 1024 ))
  (( FREE_GIB >= 25 )) || fail "Heavy QA requires at least 25 GiB free disk; detected ${FREE_GIB} GiB."
  (( FREE_GIB >= 40 )) || warn "40+ GiB free disk is recommended for model caches and Docker layers; detected ${FREE_GIB} GiB."
fi

if [[ -n "${RUNNER_OS:-}" && "$RUNNER_OS" != "Linux" ]]; then
  fail "GitHub reports RUNNER_OS=$RUNNER_OS, expected Linux."
fi
if [[ -n "${RUNNER_ARCH:-}" && "$RUNNER_ARCH" != "X64" ]]; then
  fail "GitHub reports RUNNER_ARCH=$RUNNER_ARCH, expected X64."
fi

ok "profile=$PROFILE runner_name=${RUNNER_NAME:-local} os=${RUNNER_OS:-Linux} arch=${RUNNER_ARCH:-X64}"

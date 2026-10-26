#!/usr/bin/env bash
set -euo pipefail
PROFILE="$2"
fail() { echo "::error::[github-hosted] $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"; }

[[ "$RUNNER_OS" == "Linux" ]] || fail "Only GitHub-hosted Linux is supported."
[[ "$RUNNER_ARCH" == "X64" ]] || fail "Only GitHub-hosted x64 is supported."
[[ "$RUNNER_ENVIRONMENT" == "github-hosted" ]] || fail "Expected a GitHub-hosted runner."
need git
need bash
need python3.12
[[ "$(python3.12 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.12" ]] || fail "Python 3.12 required."

case "$PROFILE" in
  governance) ;;
  ci-frontend|critical-frontend)
    need node
    need npm
    [[ "$(node -p 'process.versions.node.split(".")[0]')" == "20" ]] || fail "Node 20 required."
    ;;
  ci-backend|critical-backend|landscape|asr|launch)
    need ffmpeg
    need ffprobe
    ffmpeg -version >/dev/null
    if [[ "$PROFILE" == "ci-backend" || "$PROFILE" == "critical-backend" || "$PROFILE" == "launch" ]]; then
      need faketime
    fi
    if [[ "$PROFILE" == "launch" ]]; then
      need node
      need npm
      [[ "$(node -p 'process.versions.node.split(".")[0]')" == "20" ]] || fail "Node 20 required."
      need docker
      docker info >/dev/null || fail "Docker daemon unavailable."
      docker compose version >/dev/null || fail "Docker Compose unavailable."
      [[ -x /usr/bin/time ]] || fail "GNU time missing."
    fi
    if [[ "$PROFILE" == "landscape" || "$PROFILE" == "asr" ]]; then
      [[ -x /usr/bin/time ]] || fail "GNU time missing."
    fi
    ;;
  *) fail "Unknown profile '$PROFILE'." ;;
esac

# Never weaken the evidence requirements just to produce a green check.
if [[ "$PROFILE" == "launch" || "$PROFILE" == "asr" ]]; then
  mem_mib=$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)
  (( mem_mib >= 7400 )) || fail "Heavy QA requires at least 7400 MiB visible RAM (found $mem_mib)."
  free_gib=$(df -Pk "$RUNNER_TEMP" | awk 'NR==2 {printf "%d", $4/1024/1024}')
  (( free_gib >= 25 )) || fail "Heavy QA requires 25 GiB free disk after cleanup (found $free_gib)."
fi
echo "[github-hosted] OK profile=$PROFILE runner=$RUNNER_NAME"

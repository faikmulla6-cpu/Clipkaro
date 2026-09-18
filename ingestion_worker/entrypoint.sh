#!/bin/sh
set -eu

node /opt/bgutil/server/build/main.js --port 4416 --host 127.0.0.1 &
POT_PID=$!
trap 'kill "$POT_PID" 2>/dev/null || true' EXIT INT TERM

python - <<'PY'
import time
import urllib.request
for _ in range(40):
    try:
        with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=1) as response:
            if response.status == 200:
                break
    except Exception:
        time.sleep(0.25)
else:
    raise SystemExit("PO token provider did not become ready")
PY

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1

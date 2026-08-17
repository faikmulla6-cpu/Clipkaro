#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.hostinger.yml}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_DIR="/app/storage/backups"
REMOTE_FILE="$REMOTE_DIR/clipkaro-$STAMP.db"
LOCAL_FILE="$BACKUP_DIR/clipkaro-$STAMP.db"

mkdir -p "$BACKUP_DIR"

CID="$(docker compose -f "$COMPOSE_FILE" ps -q api)"
if [[ -z "$CID" ]]; then
  echo "ERROR: ClipKaro API container is not running." >&2
  exit 1
fi

# SQLite's online backup API produces a transactionally consistent snapshot
# without stopping the API/worker. The source DB is never copied byte-for-byte
# while writers may be active.
docker compose -f "$COMPOSE_FILE" exec -T api python - "$REMOTE_FILE" <<'PY'
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

source = Path("/app/storage/clipkaro.db")
target = Path(sys.argv[1])
if not source.exists():
    raise SystemExit("source database is missing")
target.parent.mkdir(parents=True, exist_ok=True)

with sqlite3.connect(source) as src:
    integrity = src.execute("PRAGMA integrity_check").fetchone()
    if not integrity or integrity[0] != "ok":
        raise SystemExit("source database integrity check failed")
    with sqlite3.connect(target) as dst:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")

with sqlite3.connect(target) as check:
    integrity = check.execute("PRAGMA integrity_check").fetchone()
    fk_errors = list(check.execute("PRAGMA foreign_key_check"))
    if not integrity or integrity[0] != "ok" or fk_errors:
        target.unlink(missing_ok=True)
        raise SystemExit("backup validation failed")

print(target.name)
PY

docker cp "$CID:$REMOTE_FILE" "$LOCAL_FILE"
docker compose -f "$COMPOSE_FILE" exec -T api rm -f "$REMOTE_FILE"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$LOCAL_FILE" > "$LOCAL_FILE.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$LOCAL_FILE" > "$LOCAL_FILE.sha256"
fi

# Local retention is convenience only. Production operations should also copy
# backups to a separate machine/object store; a VPS-local backup is not offsite.
find "$BACKUP_DIR" -type f \( -name 'clipkaro-*.db' -o -name 'clipkaro-*.db.sha256' \) -mtime "+$RETENTION_DAYS" -delete

echo "Backup created: $LOCAL_FILE"
echo "IMPORTANT: copy this backup off the VPS to independent storage."

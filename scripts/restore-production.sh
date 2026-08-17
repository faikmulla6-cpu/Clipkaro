#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.hostinger.yml}"
BACKUP_FILE="${1:-}"
CONFIRM="${RESTORE_CONFIRM:-}"
REMOTE_FILE="/app/storage/restore-candidate.db"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: RESTORE_CONFIRM=RESTORE_CLIPKARO $0 /path/to/clipkaro-backup.db" >&2
  exit 2
fi
BACKUP_FILE="$(cd "$(dirname "$BACKUP_FILE")" && pwd)/$(basename "$BACKUP_FILE")"
if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: backup file does not exist." >&2
  exit 1
fi
if [[ "$CONFIRM" != "RESTORE_CLIPKARO" ]]; then
  echo "ERROR: restore is destructive. Set RESTORE_CONFIRM=RESTORE_CLIPKARO after verifying the backup and maintenance window." >&2
  exit 2
fi

# Validate the backup before touching production. Never accept a corrupt SQLite
# file as a restore candidate.
python3 - "$BACKUP_FILE" <<'PY'
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
    integrity = db.execute("PRAGMA integrity_check").fetchone()
    fk = list(db.execute("PRAGMA foreign_key_check"))
if not integrity or integrity[0] != "ok" or fk:
    raise SystemExit("backup validation failed")
print("Backup integrity: PASS")
PY

# If a checksum produced by backup-production.sh is beside the backup, require it
# to match before continuing.
if [[ -f "$BACKUP_FILE.sha256" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "$BACKUP_FILE")" && sha256sum -c "$(basename "$BACKUP_FILE").sha256")
  elif command -v shasum >/dev/null 2>&1; then
    EXPECTED="$(awk '{print $1}' "$BACKUP_FILE.sha256")"
    ACTUAL="$(shasum -a 256 "$BACKUP_FILE" | awk '{print $1}')"
    [[ "$EXPECTED" == "$ACTUAL" ]] || { echo "ERROR: backup checksum mismatch." >&2; exit 1; }
  fi
fi

# Take a fresh rollback snapshot of the database we are about to replace.
# Operators should copy that safety backup off-host as well.
COMPOSE_FILE="$COMPOSE_FILE" "$ROOT/scripts/backup-production.sh"

CID="$(docker compose -f "$COMPOSE_FILE" ps -q api)"
if [[ -z "$CID" ]]; then
  echo "ERROR: ClipKaro API container must be running before staging a restore candidate." >&2
  exit 1
fi

docker cp "$BACKUP_FILE" "$CID:$REMOTE_FILE"

echo "Stopping request/media workers for an offline SQLite restore..."
docker compose -f "$COMPOSE_FILE" stop web api worker

restore_failed=0
docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint python api - "$REMOTE_FILE" <<'PY' || restore_failed=1
from __future__ import annotations
import os
import shutil
import sqlite3
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path("/app/storage/clipkaro.db")
staged = destination.with_suffix(".db.restore-tmp")
if not source.is_file():
    raise SystemExit("staged restore candidate is missing")

shutil.copy2(source, staged)
with sqlite3.connect(staged) as db:
    integrity = db.execute("PRAGMA integrity_check").fetchone()
    fk = list(db.execute("PRAGMA foreign_key_check"))
if not integrity or integrity[0] != "ok" or fk:
    staged.unlink(missing_ok=True)
    raise SystemExit("staged restore validation failed")

# With API and worker stopped there are no writers. Remove stale WAL/SHM sidecars
# before atomically replacing the main DB so pages from the previous database can
# never be replayed against the restored snapshot.
for suffix in ("-wal", "-shm"):
    Path(str(destination) + suffix).unlink(missing_ok=True)
os.replace(staged, destination)
source.unlink(missing_ok=True)

with sqlite3.connect(destination) as db:
    integrity = db.execute("PRAGMA integrity_check").fetchone()
    fk = list(db.execute("PRAGMA foreign_key_check"))
if not integrity or integrity[0] != "ok" or fk:
    raise SystemExit("restored database failed post-replacement validation")
print("Restored database integrity: PASS")
PY

if [[ "$restore_failed" -ne 0 ]]; then
  echo "ERROR: restore failed while services were stopped. Use the fresh safety backup created above to recover, then restart services." >&2
  exit 1
fi

echo "Starting ClipKaro services after restore..."
docker compose -f "$COMPOSE_FILE" up -d api worker web

echo "Restore completed. Run production preflight/smoke checks before reopening paid traffic."

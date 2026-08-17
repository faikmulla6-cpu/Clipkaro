#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / "asr-threshold-lock.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the exact ClipKaro ASR threshold contract used by a qualification run.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()

    frozen = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    encoded = json.dumps(frozen["contract"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    import hashlib
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != frozen.get("threshold_sha256"):
        raise RuntimeError("Source-controlled ASR threshold lock is internally inconsistent.")
    payload = {
        "phase": args.phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_sha256": actual,
        "contract": frozen["contract"],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(payload["threshold_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.landscape_qualification import threshold_contract, threshold_contract_sha256  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the frozen landscape QA threshold contract.")
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = {
        "schema_version": "clipkaro-landscape-threshold-snapshot-v1",
        "phase": args.phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_sha256": threshold_contract_sha256(),
        "contract": threshold_contract(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": args.phase, "threshold_sha256": payload["threshold_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

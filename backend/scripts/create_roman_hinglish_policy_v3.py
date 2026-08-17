#!/usr/bin/env python3
"""Freeze Roman Hinglish Policy V3 without modifying V2 or its evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.roman_hinglish_policy_v3 import policy_payload, policy_sha256


def main() -> int:
    target = ROOT / "roman-hinglish-policy-v3.json"
    payload = {"ROMAN_HINGLISH_POLICY_V3_SHA256": policy_sha256(), **policy_payload()}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != encoded:
        raise RuntimeError("Policy V3 already exists with different content; create V3.1 instead.")
    target.write_text(encoded, encoding="utf-8")
    print(payload["ROMAN_HINGLISH_POLICY_V3_SHA256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Safely toggle local-development Razorpay LIVE checkout.

This never prints or writes Razorpay credentials. It only changes the explicit
mode/opt-in flags in an existing private backend .env file. Production boot
rejects the development opt-in, so this cannot be carried into deployment by
accident without failing preflight.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def parse_env(text: str) -> tuple[list[str], dict[str, str]]:
    lines = text.splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return lines, values


def set_values(lines: list[str], changes: dict[str, str]) -> str:
    remaining = dict(changes)
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# Local payment-mode controls (never enable this opt-in in production).")
        out.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("enable", "disable", "status"))
    parser.add_argument("--env-file", default="backend/.env")
    args = parser.parse_args()
    path = Path(args.env_file).resolve()
    if not path.exists():
        raise SystemExit(f"Private env file does not exist: {path}")
    if path.name.endswith("example") or ".example" in path.name:
        raise SystemExit("Refusing to modify an example/template env file.")

    lines, values = parse_env(path.read_text(encoding="utf-8"))
    key_id = values.get("RAZORPAY_KEY_ID", "")
    has_secret = bool(values.get("RAZORPAY_KEY_SECRET", ""))
    mode = values.get("RAZORPAY_MODE", "test").lower()
    opt_in = values.get("ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT", "false").lower() in {"1", "true", "yes", "on"}

    if args.action == "status":
        print(f"Razorpay key type: {'LIVE' if key_id.startswith('rzp_live') else 'TEST' if key_id.startswith('rzp_test') else 'MISSING/UNKNOWN'}")
        print(f"Razorpay secret: {'configured' if has_secret else 'missing'}")
        print(f"RAZORPAY_MODE: {mode}")
        print(f"Local LIVE opt-in: {'enabled' if opt_in else 'disabled'}")
        print("No credential values were printed.")
        return 0

    if args.action == "enable":
        if not key_id.startswith("rzp_live") or not has_secret:
            raise SystemExit("Cannot enable local LIVE checkout: a LIVE Razorpay key ID and key secret must already exist in the private env file.")
        changes = {
            "RAZORPAY_MODE": "live",
            "ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT": "true",
        }
        message = "Local Razorpay LIVE checkout enabled. REAL MONEY CAN BE CHARGED. Restart the API/frontend before testing."
    else:
        changes = {
            "RAZORPAY_MODE": "test",
            "ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT": "false",
        }
        message = "Local Razorpay LIVE checkout disabled. Configure TEST keys before using test mode."

    path.write_text(set_values(lines, changes), encoding="utf-8")
    print(message)
    print("Credential values were not read aloud, changed, or printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

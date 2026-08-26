from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Stage 2J verification failed: {message}")


def main() -> None:
    manifest = json.loads((BACKEND / "release" / "founder-admin-stage2j.json").read_text(encoding="utf-8"))
    require(manifest["stage"] == "2J", "wrong manifest stage")
    require(manifest["status"] == "PREPARED_NOT_ACTIVATED", "manifest must remain non-activated")
    require(manifest["production_deployment_authorized"] is False, "manifest must not authorize deployment")
    require(manifest["activation_requires_explicit_final_approval"] is True, "explicit approval gate missing")
    require(manifest["contract"]["http_methods"] == ["GET"], "Admin contract must remain GET-only")
    require(manifest["contract"]["endpoint_count"] == 9, "Admin endpoint count changed")

    env_modal = (BACKEND / ".env.modal.example").read_text(encoding="utf-8")
    require(re.search(r"(?m)^ADMIN_API_ENABLED=false\s*$", env_modal) is not None, "production example must keep Admin API disabled")
    require(re.search(r"(?m)^ADMIN_API_SERVICE_TOKEN=\s*$", env_modal) is not None, "production example must not contain an Admin token")

    env_dev = (BACKEND / ".env.example").read_text(encoding="utf-8")
    require(re.search(r"(?m)^ADMIN_API_ENABLED=false\s*$", env_dev) is not None, "development example must keep Admin API disabled")
    require(re.search(r"(?m)^ADMIN_API_SERVICE_TOKEN=\s*$", env_dev) is not None, "development example must not contain an Admin token")

    source = (BACKEND / "app" / "api" / "founder_admin.py").read_text(encoding="utf-8")
    methods = set(re.findall(r"@router\.(get|post|put|patch|delete)\s*\(", source, flags=re.IGNORECASE))
    require(methods == {"get"}, f"Founder Admin route methods changed: {sorted(methods)}")
    require(len(re.findall(r"@router\.get\s*\(", source)) == 9, "Founder Admin must expose exactly nine GET routes")

    for forbidden in ("execute(", "execute_many(", "run_in_transaction(", "current_user", "sync_subscription_if_needed"):
        require(forbidden not in source, f"forbidden write/customer-auth dependency present: {forbidden}")

    generator = (BACKEND / "scripts" / "generate_founder_admin_token.py").read_text(encoding="utf-8")
    require("secrets.token_urlsafe(64)" in generator, "token generator must use cryptographic randomness")
    require("write_text" not in generator and "open(" not in generator, "token generator must not persist the secret")

    for name, sha in manifest["protected_refs"].items():
        require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, f"invalid pinned SHA for {name}")

    print("Stage 2J Founder Admin activation preparation: PASS")


if __name__ == "__main__":
    main()

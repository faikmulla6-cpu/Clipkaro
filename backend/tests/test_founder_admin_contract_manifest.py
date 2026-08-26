from __future__ import annotations

import json
from pathlib import Path

from app.api.founder_admin import router


def _load_contract() -> dict:
    contract_path = Path(__file__).resolve().parents[2] / "docs" / "founder-admin-contract-v1.json"
    return json.loads(contract_path.read_text(encoding="utf-8"))


def test_founder_admin_contract_manifest_matches_fastapi_routes() -> None:
    contract = _load_contract()

    assert contract["contract"] == "clipkaro-founder-admin"
    assert contract["version"] == 1
    assert contract["mode"] == "read_only"
    assert contract["write_methods_allowed"] == []
    assert contract["failure_modes"] == {
        "disabled": 404,
        "weak_backend_token": 503,
        "unauthorized": 401,
    }

    expected = {
        (item.get("path") or item.get("path_template"), item["method"])
        for item in contract["endpoints"]
    }
    assert len(expected) == 9
    assert {method for _, method in expected} == {"GET"}

    actual: set[tuple[str, str]] = set()
    for route in router.routes:
        route_path = getattr(route, "path", "")
        if not route_path.startswith("/admin"):
            continue
        path = f"/api/v1{route_path}"
        for method in getattr(route, "methods", set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            actual.add((path, method))

    assert actual == expected


def test_founder_admin_contract_declares_no_write_methods() -> None:
    contract = _load_contract()
    assert contract["write_methods_allowed"] == []
    assert all(item["method"] == "GET" for item in contract["endpoints"])

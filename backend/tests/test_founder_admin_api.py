from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import execute, fetch_one
from app.main import app


_TEST_ADMIN_TOKEN = "ck-admin-test-0123456789ABCDEF0123456789abcdef-Stage2C-ReadOnly"


@pytest.fixture()
def admin_client(tmp_path, monkeypatch):
    settings = get_settings()
    original = {
        "app_env": settings.app_env,
        "database_path": settings.database_path,
        "storage_root": settings.storage_root,
        "secret_key": settings.secret_key,
        "seed_demo_user": settings.seed_demo_user,
    }
    settings.app_env = "test"
    settings.database_path = tmp_path / "admin-api.db"
    settings.storage_root = tmp_path / "storage"
    settings.secret_key = "founder-admin-api-test-secret"
    settings.seed_demo_user = True
    monkeypatch.setenv("ADMIN_API_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_SERVICE_TOKEN", _TEST_ADMIN_TOKEN)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def _headers(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_founder_admin_surface_is_hidden_when_disabled(admin_client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_API_ENABLED", "false")
    response = admin_client.get("/api/v1/admin/overview", headers=_headers())
    assert response.status_code == 404


def test_founder_admin_rejects_missing_and_invalid_service_tokens(admin_client: TestClient):
    assert admin_client.get("/api/v1/admin/overview").status_code == 401
    assert admin_client.get("/api/v1/admin/overview", headers=_headers("wrong-token")).status_code == 401


def test_founder_admin_rejects_weak_configured_service_token(admin_client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_API_SERVICE_TOKEN", "too-short")
    response = admin_client.get("/api/v1/admin/overview", headers=_headers("too-short"))
    assert response.status_code == 503


def test_founder_admin_reads_do_not_mutate_user_state(admin_client: TestClient):
    before = asyncio.run(fetch_one("SELECT * FROM users WHERE id='demo-user'"))
    assert before

    endpoints = (
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/users/demo-user",
        "/api/v1/admin/projects",
        "/api/v1/admin/jobs",
        "/api/v1/admin/billing/summary",
        "/api/v1/admin/usage",
        "/api/v1/admin/system-health",
        "/api/v1/admin/audit",
    )
    for endpoint in endpoints:
        response = admin_client.get(endpoint, headers=_headers())
        assert response.status_code == 200, (endpoint, response.text)

    after = asyncio.run(fetch_one("SELECT * FROM users WHERE id='demo-user'"))
    assert after == before


def test_founder_admin_user_payload_excludes_credentials_and_provider_reference(admin_client: TestClient):
    response = admin_client.get("/api/v1/admin/users", headers=_headers())
    assert response.status_code == 200
    item = next(row for row in response.json()["items"] if row["id"] == "demo-user")
    assert "password_hash" not in item
    assert "billing_reference" not in item
    assert "session_version" not in item

    detail = admin_client.get("/api/v1/admin/users/demo-user", headers=_headers())
    assert detail.status_code == 200
    user = detail.json()["user"]
    assert "password_hash" not in user
    assert "billing_reference" not in user


def test_founder_admin_audit_metadata_redacts_secret_fields(admin_client: TestClient):
    asyncio.run(
        execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "admin-audit-redaction-test",
                "demo-user",
                "test.secret_metadata",
                "test",
                "entity-1",
                json.dumps({
                    "plan": "creator",
                    "token": "do-not-return",
                    "access_token": "do-not-return-either",
                    "client-secret": "also-hidden",
                    "nested": {"password": "hidden"},
                    "message": "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
                }),
                "2026-08-26T00:00:00+00:00",
            ),
        )
    )
    response = admin_client.get("/api/v1/admin/audit", headers=_headers())
    assert response.status_code == 200
    item = next(row for row in response.json()["items"] if row["id"] == "admin-audit-redaction-test")
    assert item["metadata"]["plan"] == "creator"
    assert item["metadata"]["token"] == "[redacted]"
    assert item["metadata"]["access_token"] == "[redacted]"
    assert item["metadata"]["client-secret"] == "[redacted]"
    assert item["metadata"]["nested"]["password"] == "[redacted]"
    assert item["metadata"]["message"] == "[redacted]"


def test_founder_admin_module_has_no_write_database_dependency():
    import app.api.founder_admin as module

    assert not hasattr(module, "execute")
    assert not hasattr(module, "run_in_transaction")

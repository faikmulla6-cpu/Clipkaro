from __future__ import annotations

from app.core.config import get_settings
from app.services.production_configuration import production_boot_configuration_issues


_STRONG_ADMIN_TOKEN = "ck-admin-stage2g-0123456789ABCDEF0123456789abcdef-ProductionReadiness"


def _admin_blockers() -> set[str]:
    return {
        code
        for code in production_boot_configuration_issues()
        if code.startswith("FOUNDER_ADMIN_")
    }


def test_founder_admin_disabled_has_no_admin_boot_blocker(monkeypatch):
    monkeypatch.setenv("ADMIN_API_ENABLED", "false")
    monkeypatch.delenv("ADMIN_API_SERVICE_TOKEN", raising=False)
    assert _admin_blockers() == set()


def test_founder_admin_enabled_with_weak_token_fails_closed(monkeypatch):
    monkeypatch.setenv("ADMIN_API_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_SERVICE_TOKEN", "too-short")
    assert "FOUNDER_ADMIN_SERVICE_TOKEN_WEAK" in _admin_blockers()


def test_founder_admin_enabled_with_dedicated_strong_token_passes_admin_gate(monkeypatch):
    monkeypatch.setenv("ADMIN_API_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_SERVICE_TOKEN", _STRONG_ADMIN_TOKEN)
    assert _admin_blockers() == set()


def test_founder_admin_rejects_secret_reuse_without_leaking_value(monkeypatch):
    settings = get_settings()
    original = settings.secret_key
    settings.secret_key = _STRONG_ADMIN_TOKEN
    monkeypatch.setenv("ADMIN_API_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_SERVICE_TOKEN", _STRONG_ADMIN_TOKEN)
    try:
        blockers = production_boot_configuration_issues()
    finally:
        settings.secret_key = original

    assert "FOUNDER_ADMIN_SERVICE_TOKEN_REUSED" in blockers
    assert all(_STRONG_ADMIN_TOKEN not in blocker for blocker in blockers)

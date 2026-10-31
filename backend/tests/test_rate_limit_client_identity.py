"""Regression checks: callers cannot choose their rate-limit identity on Modal."""
import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse

import app.main as main
from app.core.config import get_settings


def _request(peer: str | None, *, spoof: str, path: str = "/api/v1/auth/login") -> Request:
    headers = [
        (b"x-clipkaro-client-ip", spoof.encode("ascii")),
        (b"x-forwarded-for", b"198.51.100.99"),
        (b"cf-connecting-ip", b"198.51.100.98"),
    ]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "server": ("api.modal.run", 443),
        "client": (peer, 54321) if peer else None,
    })


def test_production_rate_limit_uses_asgi_client_not_forged_headers(monkeypatch):
    settings = get_settings()
    original = settings.app_env
    monkeypatch.setenv("JOB_EXECUTION_PROVIDER", "modal")
    settings.app_env = "production"
    try:
        assert main._rate_limit_client_key(_request("203.0.113.21", spoof="192.0.2.1")) == "203.0.113.21"
        assert main._rate_limit_client_key(_request("203.0.113.21", spoof="192.0.2.2")) == "203.0.113.21"
        assert main._rate_limit_client_key(_request("203.0.113.22", spoof="192.0.2.1")) == "203.0.113.22"
        assert main._rate_limit_client_key(_request(None, spoof="192.0.2.1")) == "unknown"
    finally:
        settings.app_env = original


def test_login_middleware_uses_same_distributed_bucket_for_forged_headers(monkeypatch):
    settings = get_settings()
    original = settings.app_env
    main._requests.clear()
    main._auth_requests.clear()
    seen = []

    async def fake_consume(identity: str, *, group: str, limit: int, window_seconds: int = 60) -> bool:
        seen.append((identity, group, limit))
        return True

    async def respond(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    monkeypatch.setattr(main, "consume_rate_limit", fake_consume)
    monkeypatch.setenv("JOB_EXECUTION_PROVIDER", "modal")
    settings.app_env = "production"
    try:
        for forged in ("192.0.2.10", "192.0.2.11"):
            result = asyncio.run(main.security_and_rate_limit(
                _request("203.0.113.77", spoof=forged), respond,
            ))
            assert result.status_code == 200

        assert seen == [
            ("203.0.113.77", "all", 180),
            ("203.0.113.77", "auth", 12),
            ("203.0.113.77", "all", 180),
            ("203.0.113.77", "auth", 12),
        ]
        assert len(main._requests["203.0.113.77"]) == 2
        assert len(main._auth_requests["203.0.113.77"]) == 2
        assert "192.0.2.10" not in main._requests
        assert "192.0.2.11" not in main._requests
    finally:
        settings.app_env = original
        main._requests.clear()
        main._auth_requests.clear()

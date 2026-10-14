from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.database import init_db
from app.services.jobs import init_job_queue, record_worker_heartbeat, worker_runtime_snapshot
from app.services import production_preflight


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_preflight_contract_is_secret_safe_and_backward_compatible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    original = {name: getattr(settings, name) for name in (
        "app_env", "job_execution_mode", "storage_root", "upload_scan_required",
        "email_verification_required", "require_forced_alignment", "groq_ranking_enabled",
    )}
    production_preflight.clear_preflight_probe_cache()
    settings.app_env = "production"
    settings.job_execution_mode = "worker"
    settings.storage_root = tmp_path / "storage"
    settings.upload_scan_required = True
    settings.email_verification_required = True
    settings.require_forced_alignment = True
    settings.groq_ranking_enabled = True

    now = datetime.now(timezone.utc).isoformat()
    worker = {
        "status": "ready", "heartbeat_at": now,
        "capabilities": {
            "whisper": {"runtime_ready": True, "model_configured": True, "model_cache_writable": True},
            "alignment": {"ready": True, "backend": "whisperx"},
            "groq": {"code": "ready"},
        },
    }
    async def fake_worker(): return worker
    async def fake_clamav(): return {"configured": True, "reachable": True, "code": "ready"}
    async def fake_smtp(*, live=True): return {"configured": True, "reachable": True, "authenticated": True, "code": "ready"}
    async def fake_razorpay(*, live=True): return {"configured": True, "reachable": True, "authenticated": True, "code": "ready"}
    monkeypatch.setattr(production_preflight, "worker_runtime_snapshot", fake_worker)
    monkeypatch.setattr(production_preflight, "probe_clamav_readiness", fake_clamav)
    monkeypatch.setattr(production_preflight, "probe_smtp_readiness", fake_smtp)
    monkeypatch.setattr(production_preflight, "probe_razorpay_readiness", fake_razorpay)
    monkeypatch.setattr(production_preflight, "ffmpeg_available", lambda: True)
    async def fake_api_asr(): return {"mode": "api", "primary_provider": "groq", "primary_status": "configured", "fallback_provider": "cloudflare", "fallback_status": "configured", "api_asr_ready": True}
    monkeypatch.setattr(production_preflight, "probe_api_asr_readiness", fake_api_asr)
    monkeypatch.setattr(production_preflight, "legal_configuration_issues", lambda: [])
    monkeypatch.setattr(production_preflight, "legal_paid_launch_ready", lambda: True)
    monkeypatch.setattr(production_preflight, "paid_launch_configuration_issues", lambda: [])
    try:
        result = asyncio.run(production_preflight.production_preflight())
    finally:
        for name, value in original.items(): setattr(settings, name, value)

    assert result["ready"] is True
    assert result["paid_launch_ready"] is True
    assert result["checks"]["ffmpeg"] is True
    assert result["checks"]["whisper"] is True
    assert result["components"]["worker"]["status"] == "pass"
    assert result["components"]["smtp"]["status"] == "pass"
    assert result["components"]["razorpay"]["status"] == "pass"
    serialized = repr(result).lower()
    for forbidden in ("password", "secret_key", "api_key", "bearer ", "smtp_host", "razorpay_key"):
        assert forbidden not in serialized


def test_paid_launch_fails_closed_without_breaking_processing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    original = {name: getattr(settings, name) for name in (
        "app_env", "job_execution_mode", "storage_root", "upload_scan_required",
        "email_verification_required", "require_forced_alignment", "groq_ranking_enabled",
    )}
    production_preflight.clear_preflight_probe_cache()
    settings.app_env = "production"
    settings.job_execution_mode = "worker"
    settings.storage_root = tmp_path / "storage"
    settings.upload_scan_required = True
    settings.email_verification_required = True
    settings.require_forced_alignment = True
    settings.groq_ranking_enabled = True
    worker = {
        "status": "ready", "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "capabilities": {
            "whisper": {"runtime_ready": True, "model_configured": True, "model_cache_writable": True},
            "alignment": {"ready": True}, "groq": {"code": "unreachable"},
        },
    }
    async def fake_worker(): return worker
    async def fake_clamav(): return {"configured": True, "reachable": True, "code": "ready"}
    async def bad_smtp(*, live=True): return {"configured": True, "reachable": False, "authenticated": False, "code": "unavailable"}
    async def bad_razorpay(*, live=True): return {"configured": False, "reachable": False, "authenticated": False, "code": "unconfigured"}
    monkeypatch.setattr(production_preflight, "worker_runtime_snapshot", fake_worker)
    monkeypatch.setattr(production_preflight, "probe_clamav_readiness", fake_clamav)
    monkeypatch.setattr(production_preflight, "probe_smtp_readiness", bad_smtp)
    monkeypatch.setattr(production_preflight, "probe_razorpay_readiness", bad_razorpay)
    monkeypatch.setattr(production_preflight, "ffmpeg_available", lambda: True)
    async def fake_api_asr(): return {"mode": "api", "primary_provider": "groq", "primary_status": "configured", "fallback_provider": "cloudflare", "fallback_status": "configured", "api_asr_ready": True}
    monkeypatch.setattr(production_preflight, "probe_api_asr_readiness", fake_api_asr)
    monkeypatch.setattr(production_preflight, "legal_configuration_issues", lambda: ["LEGAL_OPERATOR_NAME"])
    monkeypatch.setattr(production_preflight, "legal_paid_launch_ready", lambda: False)
    monkeypatch.setattr(production_preflight, "paid_launch_configuration_issues", lambda: ["PRODUCTION_CREDENTIAL_ROTATION_UNCONFIRMED"])
    try:
        result = asyncio.run(production_preflight.production_preflight())
    finally:
        for name, value in original.items(): setattr(settings, name, value)

    # Upload processing remains available: email/billing/legal are launch gates, not media-engine gates.
    assert result["ready"] is True
    assert result["paid_launch_ready"] is False
    blocked = {item["component"] for item in result["blockers"]}
    assert {"smtp", "razorpay", "legal"}.issubset(blocked)
    assert result["components"]["groq"]["status"] == "warn"


def test_stale_worker_is_a_processing_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    old_env, old_mode, old_stale, old_asr = settings.app_env, settings.job_execution_mode, settings.worker_stale_after_seconds, settings.asr_mode
    settings.app_env = "production"
    settings.job_execution_mode = "worker"
    settings.asr_mode = "local"
    settings.worker_stale_after_seconds = 30
    stale = {
        "status": "ready",
        "heartbeat_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "capabilities": {"whisper": {"runtime_ready": True, "model_configured": True, "model_cache_writable": True}, "alignment": {"ready": True}, "groq": {"code": "ready"}},
    }
    try:
        components, problems = production_preflight._worker_components(stale)
    finally:
        settings.app_env, settings.job_execution_mode, settings.worker_stale_after_seconds, settings.asr_mode = old_env, old_mode, old_stale, old_asr
    assert components["worker"]["status"] == "fail"
    assert components["whisper"]["status"] == "fail"
    assert problems


def test_api_asr_worker_does_not_require_local_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    original = settings.asr_mode, settings.job_execution_mode
    settings.asr_mode, settings.job_execution_mode = "api", "worker"
    healthy = {
        "status": "ready",
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "capabilities": {
            "whisper": {"runtime_ready": False, "model_configured": False, "model_cache_writable": True},
            "alignment": {"ready": True, "backend": "provider_native"},
            "asr": {"api_asr_ready": True},
            "groq": {"code": "ready"},
        },
    }
    try:
        components, problems = production_preflight._worker_components(healthy)
    finally:
        settings.asr_mode, settings.job_execution_mode = original
    assert components["worker"]["status"] == "pass"
    assert components["whisper"]["status"] == "disabled"
    assert not any("Whisper" in problem for problem in problems)


def test_api_asr_reports_provider_readiness_independently_of_worker_liveness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = get_settings()
    original = settings.asr_mode, settings.job_execution_mode, settings.storage_root
    settings.asr_mode, settings.job_execution_mode, settings.storage_root = "api", "worker", tmp_path / "storage"
    production_preflight.clear_preflight_probe_cache()
    async def stopped_worker(): return {"status": "missing", "capabilities": {}}
    async def ready_asr(): return {"mode": "api", "primary_provider": "groq", "primary_status": "configured", "fallback_provider": "cloudflare", "fallback_status": "configured", "api_asr_ready": True}
    monkeypatch.setattr(production_preflight, "worker_runtime_snapshot", stopped_worker)
    monkeypatch.setattr(production_preflight, "probe_api_asr_readiness", ready_asr)
    monkeypatch.setattr(production_preflight, "ffmpeg_available", lambda: True)
    try:
        result = asyncio.run(production_preflight.production_preflight())
    finally:
        settings.asr_mode, settings.job_execution_mode, settings.storage_root = original
    assert result["components"]["asr"]["status"] == "pass"
    assert result["components"]["worker"]["status"] == "fail"
    assert result["ready"] is False



def test_worker_heartbeat_round_trip_is_durable_and_secret_free(tmp_path: Path) -> None:
    settings = get_settings()
    old_backend, old_db, old_storage = settings.database_backend, settings.database_path, settings.storage_root
    # This contract intentionally exercises the local durable SQLite heartbeat
    # store. CI validates PostgreSQL separately; inheriting DATABASE_BACKEND=postgres
    # here would reuse an asyncpg pool across independent event loops and turn a
    # backend-isolation test into a false connection-concurrency failure.
    settings.database_backend = "sqlite"
    settings.database_path = tmp_path / "preflight-heartbeat.db"
    settings.storage_root = tmp_path / "storage"

    async def scenario() -> dict | None:
        await init_db()
        await init_job_queue()
        started = datetime.now(timezone.utc).isoformat()
        await record_worker_heartbeat(
            "internal-worker-id", status="ready", started_at=started,
            capabilities={
                "whisper": {"runtime_ready": True, "model_configured": True, "model_cache_writable": True},
                "alignment": {"ready": True, "backend": "whisperx"},
                "groq": {"code": "ready"},
            },
        )
        return await worker_runtime_snapshot()

    try:
        snapshot = asyncio.run(scenario())
    finally:
        settings.database_backend, settings.database_path, settings.storage_root = old_backend, old_db, old_storage
    assert snapshot and snapshot["status"] == "ready"
    assert snapshot["capabilities"]["whisper"]["runtime_ready"] is True
    assert "password" not in repr(snapshot).lower()
    assert "api_key" not in repr(snapshot).lower()


def test_source_contract_has_real_health_probes_and_heartbeat() -> None:
    routes = _read("backend/app/api/routes.py")
    preflight = _read("backend/app/services/production_preflight.py")
    jobs = _read("backend/app/services/jobs.py")
    worker = _read("backend/app/worker.py")
    scanner = _read("backend/app/services/upload_scanner.py")
    email = _read("backend/app/services/email_verification.py")
    billing = _read("backend/app/services/billing.py")
    semantic = _read("backend/app/services/semantic_ranker.py")
    compose = _read("docker-compose.hostinger.yml")

    assert 'from app.services.production_preflight import production_preflight' in routes
    assert '"paid_launch_ready"' in preflight
    assert '"components"' in preflight and '"blockers"' in preflight and '"warnings"' in preflight
    assert "worker_runtime_state" in jobs and "record_worker_heartbeat" in jobs
    assert "_worker_heartbeat_loop" in worker and "probe_groq_readiness" in worker
    assert "zPING\\0" in scanner
    assert "probe_resend_readiness" in email and "send_transactional_email" in email
    assert "https://api.razorpay.com/v1/plans" in billing
    assert "GROQ_MODELS_URL" in semantic and "models_available" in semantic
    assert "WORKER_STALE_AFTER_SECONDS" in compose and "PREFLIGHT_NETWORK_TIMEOUT_SECONDS" in compose
    assert "PRODUCTION_CREDENTIALS_ROTATED" in compose
    assert 'components["configuration"]' in preflight

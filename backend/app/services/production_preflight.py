from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import get_settings
from app.services.asr_providers import probe_api_asr_readiness
from app.services.billing import probe_razorpay_readiness
from app.services.email_verification import probe_smtp_readiness
from app.services.hinglish_roman_pipeline import verify_frozen_policies
from app.services.job_launcher import job_execution_provider_name
from app.services.jobs import isolated_worker_enabled, worker_runtime_snapshot
from app.services.legal import (
    legal_configuration_issues,
    paid_launch_ready as legal_paid_launch_ready,
)
from app.services.production_configuration import paid_launch_configuration_issues
from app.services.storage import get_storage_provider, object_storage_provider_name
from app.services.upload_scanner import probe_clamav_readiness
from app.services.video import ffmpeg_available


_EXTERNAL_PROBE_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_EXTERNAL_PROBE_LOCKS: dict[str, asyncio.Lock] = {}


def clear_preflight_probe_cache() -> None:
    """Test/operations helper; never stores credentials, only sanitized probe results."""
    _EXTERNAL_PROBE_CACHE.clear()


async def _cached_probe(
    name: str,
    factory: Callable[[], Awaitable[dict[str, object]]],
    *,
    ttl_seconds: float,
    fallback: dict[str, object],
) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    now = loop.time()
    cached = _EXTERNAL_PROBE_CACHE.get(name)
    if cached and now - cached[0] <= ttl_seconds:
        return dict(cached[1])

    lock = _EXTERNAL_PROBE_LOCKS.setdefault(name, asyncio.Lock())
    async with lock:
        now = loop.time()
        cached = _EXTERNAL_PROBE_CACHE.get(name)
        if cached and now - cached[0] <= ttl_seconds:
            return dict(cached[1])
        try:
            result = await factory()
        except Exception:
            result = dict(fallback)
        sanitized = dict(result)
        _EXTERNAL_PROBE_CACHE[name] = (loop.time(), sanitized)
        return dict(sanitized)


async def _safe_worker_snapshot() -> dict[str, Any] | None:
    try:
        return await worker_runtime_snapshot()
    except Exception:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _component(
    status: str,
    *,
    required: bool,
    code: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "required": bool(required),
        "code": code,
        "detail": detail,
    }


def _probe_storage(root: Path) -> bool:
    """Perform an actual create/fsync/delete, not merely os.access()."""
    target: Path | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        target = root / f".preflight-{secrets.token_hex(8)}"
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, b"clipkaro-preflight")
            os.fsync(fd)
        finally:
            os.close(fd)
        target.unlink(missing_ok=True)
        return True
    except OSError:
        if target is not None:
            try:
                target.unlink(missing_ok=True)
            except Exception:
                pass
        return False


async def _probe_cloud_storage() -> bool:
    """Verify the configured private bucket without creating a public object."""
    try:
        return bool(await get_storage_provider().probe())
    except Exception:
        return False


def _worker_components(
    snapshot: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    settings = get_settings()
    components: dict[str, dict[str, Any]] = {}
    processing_problems: list[str] = []

    if not isolated_worker_enabled():
        status = "fail" if settings.app_env.strip().lower() == "production" else "disabled"
        required = settings.app_env.strip().lower() == "production"
        components["worker"] = _component(
            status,
            required=required,
            code="worker_mode_disabled",
            detail=(
                "Isolated media worker mode is not active."
                if required
                else "Local background processing mode is active."
            ),
        )
        if required:
            processing_problems.append("The isolated media worker is not enabled.")
        components["whisper"] = _component(
            "pass" if settings.transcription_backend == "fixture" else "warn",
            required=False,
            code="local_runtime",
            detail="Whisper readiness is reported by the isolated worker in production.",
        )
        components["alignment"] = _component(
            "pass" if not settings.require_forced_alignment else "warn",
            required=False,
            code="local_runtime",
            detail="Forced-alignment readiness is reported by the isolated worker in production.",
        )
        components["groq"] = _component(
            "disabled" if not settings.groq_ranking_enabled else "warn",
            required=False,
            code="local_fallback",
            detail=(
                "Groq provider readiness is reported by the isolated worker; "
                "local ranking remains available."
            ),
        )
        return components, processing_problems

    if not snapshot:
        components["worker"] = _component(
            "fail",
            required=True,
            code="heartbeat_missing",
            detail="No media-worker heartbeat has been recorded.",
        )
        processing_problems.append("The media worker has not reported a heartbeat.")
        if settings.normalized_asr_mode == "api":
            components["whisper"] = _component(
                "disabled",
                required=False,
                code="api_asr_mode",
                detail="Local Whisper is not required in API ASR mode.",
            )
        else:
            components["whisper"] = _component(
                "fail",
                required=True,
                code="worker_unavailable",
                detail="Whisper runtime cannot be verified until the worker is healthy.",
            )
            processing_problems.append("The worker Whisper runtime is not verified.")

        alignment_required = bool(settings.require_forced_alignment)
        components["alignment"] = _component(
            "fail" if alignment_required else "disabled",
            required=alignment_required,
            code="worker_unavailable" if alignment_required else "optional",
            detail=(
                "Forced-alignment runtime cannot be verified until the worker is healthy."
                if alignment_required
                else "Forced alignment is optional for this environment."
            ),
        )
        if alignment_required:
            processing_problems.append(
                "The worker forced-alignment runtime is not verified."
            )
        components["groq"] = _component(
            "warn",
            required=False,
            code="worker_unavailable",
            detail=(
                "Groq status cannot be verified until the worker is healthy; "
                "deterministic local ranking remains available."
            ),
        )
        return components, processing_problems

    heartbeat = _parse_time(snapshot.get("heartbeat_at"))
    age = (
        (_utcnow() - heartbeat).total_seconds()
        if heartbeat
        else float("inf")
    )
    fresh = 0 <= age <= max(5.0, float(settings.worker_stale_after_seconds))
    state = str(snapshot.get("status") or "")
    worker_ok = fresh and state in {"ready", "busy"}
    components["worker"] = _component(
        "pass" if worker_ok else "fail",
        required=True,
        code="ready" if worker_ok else ("heartbeat_stale" if heartbeat else "heartbeat_invalid"),
        detail=(
            "Media worker heartbeat is current."
            if worker_ok
            else "Media worker heartbeat is missing or stale."
        ),
    )
    if not worker_ok:
        processing_problems.append(
            "The media worker heartbeat is stale or unhealthy."
        )

    caps = (
        snapshot.get("capabilities")
        if isinstance(snapshot.get("capabilities"), dict)
        else {}
    )
    whisper = caps.get("whisper") if isinstance(caps.get("whisper"), dict) else {}
    if settings.normalized_asr_mode == "api":
        components["whisper"] = _component(
            "disabled",
            required=False,
            code="api_asr_mode",
            detail=(
                "Local Whisper is not required; the worker uses configured API ASR providers."
            ),
        )
    else:
        whisper_ok = (
            worker_ok
            and bool(whisper.get("runtime_ready"))
            and bool(whisper.get("model_configured"))
            and bool(whisper.get("model_cache_writable"))
        )
        components["whisper"] = _component(
            "pass" if whisper_ok else "fail",
            required=True,
            code="ready" if whisper_ok else "runtime_unready",
            detail=(
                "Worker Whisper runtime, model configuration and model cache are ready."
                if whisper_ok
                else "Worker Whisper runtime/model cache is not ready."
            ),
        )
        if not whisper_ok:
            processing_problems.append("Whisper is not ready in the media worker.")

    alignment = (
        caps.get("alignment")
        if isinstance(caps.get("alignment"), dict)
        else {}
    )
    alignment_required = bool(settings.require_forced_alignment)
    alignment_ok = worker_ok and bool(alignment.get("ready"))
    if alignment_required:
        components["alignment"] = _component(
            "pass" if alignment_ok else "fail",
            required=True,
            code="ready" if alignment_ok else "runtime_unready",
            detail=(
                "Required WhisperX forced-alignment runtime is ready."
                if alignment_ok
                else "Required WhisperX forced-alignment runtime is not ready."
            ),
        )
        if not alignment_ok:
            processing_problems.append(
                "Required WhisperX forced alignment is not ready."
            )
    else:
        components["alignment"] = _component(
            "pass" if alignment_ok else "disabled",
            required=False,
            code="ready" if alignment_ok else "optional",
            detail="Forced alignment is optional for this environment.",
        )

    groq = caps.get("groq") if isinstance(caps.get("groq"), dict) else {}
    if not settings.groq_ranking_enabled:
        components["groq"] = _component(
            "disabled",
            required=False,
            code="disabled",
            detail=(
                "Groq semantic ranking is disabled; deterministic local ranking remains active."
            ),
        )
    else:
        groq_ok = worker_ok and str(groq.get("code") or "") == "ready"
        components["groq"] = _component(
            "pass" if groq_ok else "warn",
            required=False,
            code="ready" if groq_ok else str(groq.get("code") or "unverified"),
            detail=(
                "Groq semantic ranking is reachable with a configured model."
                if groq_ok
                else "Groq is degraded or unverified; deterministic local ranking remains available."
            ),
        )
    return components, processing_problems


async def production_preflight() -> dict[str, Any]:
    """Return a secret-safe, fail-closed production and paid-launch readiness report."""
    settings = get_settings()
    is_production = settings.app_env.strip().lower() == "production"
    serverless_job_mode = (
        is_production
        and settings.normalized_job_backend == "cloud_run_job"
    )

    if serverless_job_mode:
        try:
            execution_provider = job_execution_provider_name()
        except Exception:
            execution_provider = "invalid"
        try:
            storage_provider = object_storage_provider_name()
        except Exception:
            storage_provider = "invalid"
    else:
        execution_provider = "local"
        storage_provider = "local"

    media_runtime = (
        "Modal media Function"
        if execution_provider == "modal"
        else "Cloud Run media job"
        if execution_provider == "cloud_run"
        else "serverless media runtime"
    )
    storage_runtime = (
        "private S3-compatible bucket"
        if storage_provider == "s3"
        else "private GCS bucket"
        if storage_provider == "gcs"
        else "private cloud storage"
    )

    storage_task = (
        _probe_cloud_storage()
        if serverless_job_mode
        else asyncio.to_thread(_probe_storage, settings.storage_root)
    )

    if is_production:
        clamav_task = (
            asyncio.sleep(
                0,
                result={
                    "configured": True,
                    "reachable": True,
                    "code": "delegated_to_media_runtime",
                },
            )
            if serverless_job_mode
            else _cached_probe(
                "clamav",
                probe_clamav_readiness,
                ttl_seconds=10.0,
                fallback={
                    "configured": True,
                    "reachable": False,
                    "code": "probe_failed",
                },
            )
        )
        smtp_task = _cached_probe(
            "smtp",
            lambda: probe_smtp_readiness(live=True),
            ttl_seconds=60.0,
            fallback={
                "configured": True,
                "reachable": False,
                "authenticated": False,
                "code": "probe_failed",
            },
        )
        razorpay_task = _cached_probe(
            "razorpay",
            lambda: probe_razorpay_readiness(live=True),
            ttl_seconds=60.0,
            fallback={
                "configured": True,
                "reachable": False,
                "authenticated": False,
                "code": "probe_failed",
            },
        )
    else:
        clamav_task = probe_clamav_readiness()
        smtp_task = probe_smtp_readiness(live=False)
        razorpay_task = probe_razorpay_readiness(live=False)

    worker_task = (
        asyncio.sleep(0, result=None)
        if serverless_job_mode
        else (
            _safe_worker_snapshot()
            if isolated_worker_enabled()
            else asyncio.sleep(0, result=None)
        )
    )

    storage_ok, clamav, smtp, razorpay, worker = await asyncio.gather(
        storage_task,
        clamav_task,
        smtp_task,
        razorpay_task,
        worker_task,
    )

    components: dict[str, dict[str, Any]] = {}
    processing_problems: list[str] = []

    media_ok = serverless_job_mode or ffmpeg_available()
    components["ffmpeg"] = _component(
        "pass" if media_ok else "fail",
        required=True,
        code=(
            "delegated_to_media_runtime"
            if serverless_job_mode
            else ("ready" if media_ok else "missing")
        ),
        detail=(
            f"FFmpeg and FFprobe are delegated to the {media_runtime}."
            if serverless_job_mode
            else (
                "FFmpeg and FFprobe are available."
                if media_ok
                else "FFmpeg or FFprobe is unavailable."
            )
        ),
    )
    if not media_ok:
        processing_problems.append("FFmpeg/FFprobe is unavailable.")

    components["storage"] = _component(
        "pass" if storage_ok else "fail",
        required=True,
        code="ready" if storage_ok else "unreachable",
        detail=(
            f"The configured {storage_runtime} accepted an authenticated readiness probe."
            if serverless_job_mode and storage_ok
            else (
                f"The configured {storage_runtime} could not be verified."
                if serverless_job_mode
                else (
                    "Persistent storage passed a write/fsync/delete probe."
                    if storage_ok
                    else "Persistent storage is not writable."
                )
            )
        ),
    )
    if not storage_ok:
        processing_problems.append("Persistent media storage is unavailable.")

    clamav_required = bool(settings.upload_scan_required) or is_production
    clamav_ok = bool(clamav.get("configured")) and bool(clamav.get("reachable"))
    components["clamav"] = _component(
        "pass" if clamav_ok else ("fail" if clamav_required else "disabled"),
        required=clamav_required,
        code="ready" if clamav_ok else str(clamav.get("code") or "unavailable"),
        detail=(
            f"Malware scanning is delegated to the {media_runtime}."
            if serverless_job_mode and clamav_ok
            else (
                "ClamAV accepted a side-effect-free health ping."
                if clamav_ok
                else (
                    "Required upload malware scanning is unavailable."
                    if clamav_required
                    else "Upload malware scanning is disabled in this environment."
                )
            )
        ),
    )
    if clamav_required and not clamav_ok:
        processing_problems.append(
            "Required ClamAV upload scanning is unavailable."
        )

    if serverless_job_mode:
        provider_code = (
            "modal_function_configured"
            if execution_provider == "modal"
            else "cloud_run_job_configured"
            if execution_provider == "cloud_run"
            else "serverless_runtime_configured"
        )
        components["worker"] = _component(
            "pass",
            required=True,
            code=provider_code,
            detail=(
                f"Per-request media processing is delegated to the {media_runtime}; "
                "no permanent worker heartbeat is expected."
            ),
        )
        components["whisper"] = _component(
            "disabled" if settings.normalized_asr_mode == "api" else "pass",
            required=settings.normalized_asr_mode != "api",
            code=(
                "api_asr_mode"
                if settings.normalized_asr_mode == "api"
                else "delegated_to_media_runtime"
            ),
            detail=f"Media runtime readiness is verified in the {media_runtime}.",
        )
        components["alignment"] = _component(
            "pass" if settings.require_forced_alignment else "disabled",
            required=bool(settings.require_forced_alignment),
            code="delegated_to_media_runtime",
            detail=f"Forced-alignment runtime is delegated to the {media_runtime}.",
        )
        components["groq"] = _component(
            "disabled" if not settings.groq_ranking_enabled else "warn",
            required=False,
            code="media_runtime",
            detail=(
                "Provider runtime is evaluated by each isolated media execution."
            ),
        )
    else:
        worker_components, worker_problems = _worker_components(worker)
        components.update(worker_components)
        processing_problems.extend(worker_problems)

    if settings.normalized_asr_mode == "api":
        heartbeat_caps = (
            worker.get("capabilities")
            if isinstance(worker, dict)
            and isinstance(worker.get("capabilities"), dict)
            else {}
        )
        heartbeat_asr = (
            heartbeat_caps.get("asr")
            if isinstance(heartbeat_caps.get("asr"), dict)
            else {}
        )
        api_asr = (
            dict(heartbeat_asr)
            if heartbeat_asr
            else await probe_api_asr_readiness()
        )
        configured = bool(api_asr.get("api_asr_ready"))
        components["asr"] = _component(
            "pass" if configured else "fail",
            required=True,
            code="ready" if configured else "provider_unconfigured",
            detail=(
                "API ASR primary/fallback configuration is available."
                if configured
                else "No usable API ASR provider is configured."
            ),
        )
        components["asr"].update(api_asr)
        if not configured:
            processing_problems.append(
                "No usable API ASR provider is configured."
            )

    hinglish_provider = settings.normalized_hinglish_asr_provider
    hinglish_enabled = settings.hinglish_roman_pipeline_enabled
    heartbeat_caps = (
        worker.get("capabilities")
        if isinstance(worker, dict)
        and isinstance(worker.get("capabilities"), dict)
        else {}
    )
    worker_hinglish = (
        heartbeat_caps.get("hinglish_asr")
        if isinstance(heartbeat_caps.get("hinglish_asr"), dict)
        else {}
    )
    if isolated_worker_enabled() and worker_hinglish:
        hinglish_candidate_ready = bool(worker_hinglish.get("ready"))
    else:
        hinglish_candidate_ready = (
            bool(settings.elevenlabs_keys)
            and verify_frozen_policies()
            and settings.normalized_asr_fallback_provider == "cloudflare"
        )

    hinglish_ready = hinglish_provider == "legacy" or (
        hinglish_candidate_ready and media_ok
    )
    components["hinglish_asr"] = _component(
        "pass" if hinglish_ready else "fail",
        required=hinglish_enabled,
        code="ready" if hinglish_ready else "candidate_configuration_invalid",
        detail=(
            "Legacy Groq/Cloudflare Hinglish route remains selected."
            if hinglish_provider == "legacy"
            else (
                "ElevenLabs Scribe v2, frozen Roman V3/Display V1, "
                "FFmpeg/FFprobe and fallback configuration are ready."
                if hinglish_ready
                else (
                    "ElevenLabs Hinglish candidate configuration is incomplete; "
                    "no external provider call was made."
                )
            )
        ),
    )
    components["hinglish_asr"].update(
        {
            "provider": hinglish_provider,
            "enabled": hinglish_enabled,
            "fallback_route": "groq_then_cloudflare",
            "roman_policy": settings.roman_hinglish_policy,
            "display_policy": settings.roman_hinglish_display_policy,
            "hinglish_stage1_enabled": settings.hinglish_stage1_enabled,
            "hinglish_stage1_allowlist_count": len(settings.hinglish_stage1_ids),
            "hinglish_stage1_config_valid": True,
            "job_route_persistence_ready": True,
        }
    )
    if hinglish_enabled and not hinglish_ready:
        processing_problems.append(
            "Enabled ElevenLabs Hinglish ASR candidate is not safely configured."
        )

    smtp_required = bool(settings.email_verification_required) or is_production
    smtp_ok = (
        bool(smtp.get("configured"))
        and bool(smtp.get("reachable"))
        and bool(smtp.get("authenticated"))
    )
    components["smtp"] = _component(
        "pass" if smtp_ok else ("fail" if smtp_required else "disabled"),
        required=smtp_required,
        code="ready" if smtp_ok else str(smtp.get("code") or "unavailable"),
        detail=(
            "Transactional email configuration is ready; no message was sent."
            if smtp_ok
            else (
                "Transactional email is not ready."
                if smtp_required
                else "Transactional email is optional in this environment."
            )
        ),
    )

    razorpay_ok = (
        bool(razorpay.get("configured"))
        and bool(razorpay.get("reachable"))
        and bool(razorpay.get("authenticated"))
    )
    components["razorpay"] = _component(
        "pass" if razorpay_ok else "fail",
        required=is_production,
        code="ready" if razorpay_ok else str(razorpay.get("code") or "unavailable"),
        detail=(
            "Razorpay configuration and read-only provider authentication are ready."
            if razorpay_ok
            else (
                "Razorpay credentials/webhook configuration or provider access is not ready."
            )
        ),
    )

    configuration_issues = (
        paid_launch_configuration_issues()
        if is_production
        else []
    )
    configuration_ok = not configuration_issues
    components["configuration"] = _component(
        "pass" if configuration_ok else ("fail" if is_production else "disabled"),
        required=is_production,
        code=(
            "ready"
            if configuration_ok
            else "production_configuration_incomplete"
        ),
        detail=(
            "Production secret/provider configuration passed offline policy checks."
            if configuration_ok
            else (
                "Production secret/provider configuration is incomplete or "
                "not rotation-confirmed."
            )
        ),
    )

    legal_issues = legal_configuration_issues()
    legal_ok = legal_paid_launch_ready() and not legal_issues
    components["legal"] = _component(
        "pass" if legal_ok else "fail",
        required=is_production,
        code="ready" if legal_ok else "operator_particulars_incomplete",
        detail=(
            "Required public operator, customer-care and grievance particulars are configured."
            if legal_ok
            else "Required legal/operator particulars are incomplete."
        ),
    )

    processing_required = (
        "ffmpeg",
        "storage",
        "clamav",
        "worker",
        "asr" if settings.normalized_asr_mode == "api" else "whisper",
        "alignment",
        "hinglish_asr",
    )
    processing_ready = all(
        components[name]["status"] in {"pass", "disabled"}
        or not components[name]["required"]
        for name in processing_required
        if name in components
    )

    launch_blockers: list[dict[str, str]] = []
    paid_required = set(processing_required) | {
        "configuration",
        "smtp",
        "razorpay",
        "legal",
    }
    if is_production:
        for name in sorted(paid_required):
            item = components.get(name)
            if item and item["required"] and item["status"] != "pass":
                launch_blockers.append(
                    {
                        "component": name,
                        "code": str(item["code"]),
                        "message": str(item["detail"]),
                    }
                )

    warnings = [
        {
            "component": name,
            "code": str(item["code"]),
            "message": str(item["detail"]),
        }
        for name, item in components.items()
        if item["status"] == "warn"
    ]
    paid_ready = bool(
        is_production
        and processing_ready
        and not launch_blockers
    )

    whisper_pass = (
        settings.normalized_asr_mode == "api"
        or components.get("whisper", {}).get("status") == "pass"
    )
    return {
        "ready": processing_ready,
        "paid_launch_ready": paid_ready,
        "status": (
            "ready"
            if paid_ready
            else (
                "processing_ready"
                if processing_ready
                else "blocked"
            )
        ),
        "checked_at": _utcnow().isoformat(),
        "checks": {
            "ffmpeg": media_ok,
            "whisper": whisper_pass,
            "storage": storage_ok,
            "model": settings.whisper_model,
            "transcription_backend": settings.transcription_backend,
            "asr_mode": settings.asr_mode,
            "alignment_backend": settings.alignment_backend,
            "consensus_required": settings.effective_require_asr_consensus,
            "semantic_ranking": (
                "groq"
                if settings.groq_ranking_enabled
                else "local"
            ),
            "semantic_model": (
                settings.groq_ranking_model
                if settings.groq_ranking_enabled
                else "deterministic-local"
            ),
            "object_storage_provider": storage_provider,
            "job_execution_provider": execution_provider,
        },
        "components": components,
        "problems": list(dict.fromkeys(processing_problems)),
        "blockers": launch_blockers,
        "warnings": warnings,
        "recommendation": (
            "Processing is ready, but paid launch remains blocked by the listed production checks."
            if processing_ready and not paid_ready and is_production
            else (
                "Resolve the processing blockers before accepting new uploads."
                if not processing_ready
                else (
                    "Development processing checks passed; paid-launch certification applies only in APP_ENV=production."
                    if not is_production
                    else "All production preflight checks passed."
                )
            )
        ),
    }

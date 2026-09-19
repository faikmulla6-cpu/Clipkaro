from contextlib import asynccontextmanager
import asyncio
import json
import re
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router, _process_project
from app.api.settings import init_user_preferences, router as settings_router
from app.api.billing_lifecycle import init_subscription_lifecycle, router as billing_lifecycle_router
from app.api.media import router as media_router
from app.api.email_verification import router as email_verification_router
from app.api.account_security import router as account_security_router
from app.api.secure_upload import router as secure_upload_router
from app.api.worker_jobs import router as worker_jobs_router
from app.api.cloud_uploads import init_cloud_uploads, router as cloud_uploads_router
from app.api.creator_pulse import init_creator_pulse, router as creator_pulse_router
from app.core.config import get_settings
from app.core.database import UsageQuotaExceeded, close_database, execute, fetch_all, fetch_one, init_db
from app.services.auth import current_user, hash_password
from app.services.account_security import init_account_security
from app.services.cleanup import cleanup_loop
from app.services.email_verification import init_email_verification, requires_verification_for_processing
from app.services.forced_alignment import validate_production_alignment_policy
from app.services.production_configuration import production_boot_configuration_issues
from app.services.jobs import init_job_queue, isolated_worker_enabled
from app.services.hinglish_stage1_routing import persisted_stage1_route
from app.services.storage_paths import confined_export_path
from app.services.distributed_rate_limit import consume_rate_limit
from app.core.version import APP_VERSION


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.app_env == "production":
        boot_issues = production_boot_configuration_issues()
        if boot_issues:
            raise RuntimeError(
                "Production boot configuration is invalid: " + ", ".join(boot_issues)
            )
        if not settings.production_serverless_mode:
            raise RuntimeError("Production requires PostgreSQL, GCS, and Cloud Run Jobs serverless backends.")
        if not settings.upload_scan_required:
            raise RuntimeError("Production media validation must remain fail closed.")
        # Legacy local ASR still requires WhisperX policy. API ASR deliberately
        # has provider-native timestamps and must start without that dependency.
        if settings.normalized_asr_mode == "local":
            validate_production_alignment_policy(
                settings.alignment_backend, settings.require_forced_alignment
            )
    await init_db()
    await init_job_queue()
    await init_cloud_uploads()
    # Identity schema is installed before any request can authenticate. Existing
    # stateless JWTs are intentionally retired on deploy; users sign in once to
    # receive independently revocable persisted sessions.
    await init_account_security()
    await init_user_preferences()
    await init_subscription_lifecycle()
    await init_creator_pulse()
    if settings.seed_demo_user and not await fetch_one("SELECT id FROM users WHERE email=?", (settings.demo_email,)):
        timestamp = datetime.now(timezone.utc).isoformat()
        await execute(
            "INSERT INTO users(id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at) VALUES (?, ?, ?, ?, 'creator', 'admin', 1, ?, ?)",
            ("demo-user", "Faik", settings.demo_email, hash_password(settings.demo_password), timestamp, timestamp),
        )
    # Run after the legacy/demo seed so the one-time migration can mark every
    # account that existed before verification shipped as already verified.
    await init_email_verification()

    recovery_tasks: list[asyncio.Task] = []
    # In production the network-facing API never executes media recovery. The
    # isolated worker owns durable claim recovery. Background mode is retained
    # only for tests/development so the established local lifecycle still works.
    if not isolated_worker_enabled():
        interrupted = await fetch_all("""SELECT * FROM jobs WHERE status IN ('queued','processing')
                                       ORDER BY updated_at DESC""")
        recovered_projects: set[str] = set()
        for job in interrupted:
            if job["kind"] in {"process_video", "upgrade_pipeline"} and job.get("project_id") not in recovered_projects:
                project_id = job["project_id"]
                user = await fetch_one("SELECT * FROM users WHERE id=?", (job["user_id"],))
                video = await fetch_one("SELECT * FROM videos WHERE project_id=?", (project_id,))
                project = await fetch_one("SELECT status FROM projects WHERE id=?", (project_id,))
                if project and video and project.get("status") == "ready" and video.get("status") == "ready":
                    recovered_projects.add(project_id)
                    await execute(
                        "UPDATE jobs SET status='completed',progress=100,stage='ready',message='Recovered completed project after restart',error=NULL WHERE id=?",
                        (job["id"],),
                    )
                    continue
                if user and video:
                    recovered_projects.add(project_id)
                    await execute("UPDATE jobs SET status='queued',stage='recovery',message='Resuming after restart' WHERE id=?", (job["id"],))
                    payload_row = await fetch_one("SELECT payload_json FROM job_payloads WHERE job_id=?", (job["id"],))
                    try:
                        payload = json.loads((payload_row or {}).get("payload_json") or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        payload = {}
                    route = persisted_stage1_route(payload)
                    force_transcribe = bool(payload.get("force_transcribe", False))
                    recovery_tasks.append(asyncio.create_task(
                        _process_project(
                            job["id"], project_id, video["id"], user,
                            route["asr_route"], force_transcribe,
                        )
                    ))
                    continue
            if job.get("export_id"):
                export = await fetch_one("SELECT * FROM exports WHERE id=?", (job["export_id"],))
                export_path = confined_export_path((export or {}).get("output_path"))
                if export and export.get("status") == "ready" and export_path and export_path.is_file():
                    await execute(
                        "UPDATE jobs SET status='completed',progress=100,stage='ready',message='Recovered completed export after restart',error=NULL WHERE id=?",
                        (job["id"],),
                    )
                    continue
            await execute("UPDATE jobs SET status='failed',stage='interrupted',message='Interrupted by server restart',error='Retry this operation.' WHERE id=?", (job["id"],))
            if job.get("export_id"):
                # The exports failure trigger atomically refunds a still-reserved
                # export slot. Finalized successful reservations are never refunded.
                await execute("UPDATE exports SET status='failed',error='Server restarted during export. Retry the export.' WHERE id=?", (job["export_id"],))
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        # Wait for cancellation to finish before FastAPI closes its event loop.
        # This prevents DB worker threads from trying to report results to an
        # already-closed loop during deploys, tests, or graceful VPS restarts.
        cleanup_task.cancel()
        for task in recovery_tasks:
            task.cancel()
        await asyncio.gather(cleanup_task, *recovery_tasks, return_exceptions=True)
        await close_database()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Upload-first AI Shorts generation API for content owners.",
    version=APP_VERSION,
    docs_url=None if settings.app_env == "production" else "/docs",
    lifespan=lifespan,
)


@app.exception_handler(UsageQuotaExceeded)
async def usage_quota_exceeded(_: Request, exc: UsageQuotaExceeded) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=402)


app.add_middleware(
    CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization", "X-CSRF-Token", "X-Request-ID"],
)

_requests: dict[str, deque[float]] = defaultdict(deque)
_auth_requests: dict[str, deque[float]] = defaultdict(deque)
_rate_bucket_last_prune = 0.0
_RATE_BUCKET_WINDOW_SECONDS = 60.0


def _prune_rate_limit_buckets(current: float) -> None:
    """Drop inactive client keys so rotating source IPs cannot grow maps forever.

    The limiter remains intentionally process-local for the single-API VPS
    topology. A distributed limiter is required before horizontal API scaling.
    """
    global _rate_bucket_last_prune
    if current - _rate_bucket_last_prune < _RATE_BUCKET_WINDOW_SECONDS:
        return
    for registry in (_requests, _auth_requests):
        stale = [
            key for key, values in registry.items()
            if not values or current - values[-1] > _RATE_BUCKET_WINDOW_SECONDS
        ]
        for key in stale:
            registry.pop(key, None)
    _rate_bucket_last_prune = current


def _creator_compute_request(request: Request) -> bool:
    """Return True before a normal creator request can reserve paid compute.

    The internal/manual `/analyse` endpoint is intentionally not duplicated
    here. It already has a stricter fail-closed access policy in `current_user`:
    production/staging/preview creators can never call it, while explicitly
    opted-in local development QA remains usable.
    """
    if request.method.upper() != "POST":
        return False
    path = request.url.path
    prefix = settings.api_prefix
    if path == f"{prefix}/projects/upload":
        return True
    if path == f"{prefix}/uploads/init" or (path.startswith(f"{prefix}/uploads/") and path.endswith("/complete")):
        return True
    if path.startswith(f"{prefix}/projects/") and path.endswith("/reprocess"):
        return True
    if path.startswith(f"{prefix}/clips/") and path.endswith("/export"):
        return True
    return False


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_id(request: Request) -> str:
    supplied = (request.headers.get("X-Request-ID") or "").strip()
    return supplied if _REQUEST_ID_RE.fullmatch(supplied) else str(uuid4())


def _apply_security_headers(response, request_id: str):
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _rate_limit_client_key(request: Request) -> str:
    """Return a stable per-client key without trusting arbitrary proxy headers.

    Production traffic reaches the API only through the private Caddy service in
    docker-compose. Caddy overwrites ``X-ClipKaro-Client-IP`` with
    ``{remote_host}``, so the value cannot be supplied by an Internet client.
    Development/test traffic connects directly and therefore uses the ASGI peer.
    """
    if settings.app_env == "production":
        edge_client = (request.headers.get("X-ClipKaro-Client-IP") or "").strip()
        if edge_client:
            return edge_client[:128]
    return (request.client.host if request.client else "unknown")[:128]


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    request_id = _request_id(request)
    client = _rate_limit_client_key(request)
    if settings.app_env == "production" and not await consume_rate_limit(client, group="all", limit=180):
        return _apply_security_headers(
            JSONResponse({"detail": "Too many requests. Please wait a moment."}, status_code=429, headers={"Retry-After": "60"}),
            request_id,
        )
    current = time.monotonic()
    _prune_rate_limit_buckets(current)
    bucket = _requests[client]
    while bucket and current - bucket[0] > _RATE_BUCKET_WINDOW_SECONDS:
        bucket.popleft()
    general_limit = 100000 if settings.app_env == "test" else 180
    if len(bucket) >= general_limit:
        return _apply_security_headers(
            JSONResponse({"detail": "Too many requests. Please wait a moment."}, status_code=429, headers={"Retry-After": "60"}),
            request_id,
        )
    bucket.append(current)

    auth_paths = {
        f"{settings.api_prefix}/auth/login",
        f"{settings.api_prefix}/auth/signup",
        f"{settings.api_prefix}/auth/verify-email",
        f"{settings.api_prefix}/auth/resend-verification",
        f"{settings.api_prefix}/auth/password/forgot",
        f"{settings.api_prefix}/auth/password/reset",
    }
    if request.url.path in auth_paths:
        if settings.app_env == "production" and not await consume_rate_limit(client, group="auth", limit=12):
            return _apply_security_headers(
                JSONResponse({"detail": "Too many authentication attempts. Wait one minute and retry."}, status_code=429, headers={"Retry-After": "60"}),
                request_id,
            )
        auth_bucket = _auth_requests[client]
        while auth_bucket and current - auth_bucket[0] > _RATE_BUCKET_WINDOW_SECONDS:
            auth_bucket.popleft()
        auth_limit = 100000 if settings.app_env == "test" else 12
        if len(auth_bucket) >= auth_limit:
            return _apply_security_headers(
                JSONResponse({"detail": "Too many authentication attempts. Wait one minute and retry."}, status_code=429,
                             headers={"Retry-After": "60"}),
                request_id,
            )
        auth_bucket.append(current)

    csrf_exempt = {
        f"{settings.api_prefix}/auth/login",
        f"{settings.api_prefix}/auth/signup",
        f"{settings.api_prefix}/auth/password/forgot",
        # High-entropy one-time tokens are the proof for these public endpoints;
        # the secrets are submitted in JSON, never as cookie-authenticated acts.
        f"{settings.api_prefix}/auth/password/reset",
        f"{settings.api_prefix}/auth/verify-email",
        f"{settings.api_prefix}/billing/razorpay/webhook",
    }
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path not in csrf_exempt:
        cookie_token = request.cookies.get("csrf_token")
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
            return _apply_security_headers(
                JSONResponse({"detail": "Security token missing or invalid. Refresh and try again."}, status_code=403),
                request_id,
            )

    # Server-side authority: UI redirects are convenience only. This check runs
    # before multipart upload parsing or route execution, so an unverified
    # creator cannot consume upload storage, ASR/Groq work, or FFmpeg rendering
    # by calling the normal customer API directly.
    if _creator_compute_request(request):
        try:
            user = await current_user(
                request,
                access_token=request.cookies.get("access_token"),
                authorization=request.headers.get("Authorization"),
            )
        except HTTPException as exc:
            return _apply_security_headers(
                JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code,
                    headers=exc.headers or {},
                ),
                request_id,
            )
        if requires_verification_for_processing(user):
            return _apply_security_headers(
                JSONResponse(
                    {
                        "detail": "Verify your email before starting AI processing.",
                        "code": "EMAIL_VERIFICATION_REQUIRED",
                    },
                    status_code=403,
                ),
                request_id,
            )

    response = await call_next(request)
    return _apply_security_headers(response, request_id)


# Split security-sensitive paths away from the legacy all-in-one router. Keeping
# exactly one active handler per method/path prevents an older unscanned,
# in-memory-worker or stateless implementation from remaining reachable.
_REPLACED_PATHS = {
    "/billing/status",
    "/billing/razorpay/webhook",
    "/billing/checkout",
    "/billing/verify",
    "/billing/sync",
    "/billing/cancel",
    "/projects/{project_id}/media",
    "/auth/signup",
    "/auth/login",
    "/auth/logout",
    "/projects/upload",
    "/projects/{project_id}/reprocess",
    "/clips/{clip_id}/export",
}
_REPLACED_METHOD_ROUTES = {
    ("/projects/{project_id}", "GET"),
}


def _legacy_route_is_replaced(route) -> bool:
    path = getattr(route, "path", None)
    if path in _REPLACED_PATHS:
        return True
    methods = getattr(route, "methods", set()) or set()
    return any(path == route_path and method in methods for route_path, method in _REPLACED_METHOD_ROUTES)


router.routes[:] = [route for route in router.routes if not _legacy_route_is_replaced(route)]
app.include_router(billing_lifecycle_router, prefix=settings.api_prefix)
app.include_router(media_router, prefix=settings.api_prefix)
app.include_router(account_security_router, prefix=settings.api_prefix)
app.include_router(email_verification_router, prefix=settings.api_prefix)
app.include_router(secure_upload_router, prefix=settings.api_prefix)
app.include_router(worker_jobs_router, prefix=settings.api_prefix)
app.include_router(cloud_uploads_router, prefix=settings.api_prefix)
app.include_router(creator_pulse_router, prefix=settings.api_prefix)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(settings_router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    payload = {"name": settings.app_name, "health": f"{settings.api_prefix}/health"}
    if settings.app_env != "production":
        payload["docs"] = "/docs"
    return payload

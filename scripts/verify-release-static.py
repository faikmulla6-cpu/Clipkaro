#!/usr/bin/env python3
"""Dependency-free launch artifact sanity checks for ClipKaro.

This verifier intentionally avoids importing the application so it can run in a
minimal release/build environment before Python/Node dependencies are installed.
It checks packaging, production fail-closed defaults, critical route wiring and
security-sensitive release invariants. It does not replace pytest, a Next build,
Docker validation, or real provider/webhook smoke tests.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASS = 0
FAIL = 0


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        suffix = f" — {detail}" if detail else ""
        print(f"FAIL  {label}{suffix}")


def version_tuple(value: str) -> tuple[int, ...]:
    core = value.lstrip("^~v").split("-", 1)[0]
    return tuple(int(part) for part in core.split("."))


# --- API router wiring -----------------------------------------------------
main = text("backend/app/main.py")
expected_router_symbols = {
    "billing_lifecycle_router",
    "media_router",
    "account_security_router",
    "email_verification_router",
    "secure_upload_router",
    "worker_jobs_router",
    "legal_router",
    "behavioral_learning_router",
    "router",
    "settings_router",
}
for symbol in sorted(expected_router_symbols):
    check(
        f"API router included: {symbol}",
        f"app.include_router({symbol}," in main,
        "router exists but is not mounted in FastAPI",
    )

# --- Route uniqueness / canonical ownership -----------------------------------
route_map: dict[tuple[str, str], list[str]] = defaultdict(list)
for api_file in sorted((ROOT / "backend/app/api").glob("*.py")):
    try:
        tree = ast.parse(api_file.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        check(f"API syntax: {api_file.name}", False, str(exc))
        continue
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            route_map[(decorator.func.attr.upper(), decorator.args[0].value)].append(
                f"{api_file.name}:{node.name}"
            )
duplicates = {key: owners for key, owners in route_map.items() if len(owners) > 1}
check(
    "no duplicate API method/path registrations",
    not duplicates,
    "; ".join(f"{method} {path} -> {owners}" for (method, path), owners in sorted(duplicates.items())),
)
canonical_routes = {
    ("POST", "/auth/signup"): "email_verification.py:signup_with_verification",
    ("POST", "/auth/login"): "account_security.py:login",
    ("POST", "/auth/logout"): "account_security.py:logout",
    ("POST", "/billing/checkout"): "billing_lifecycle.py:billing_checkout",
    ("POST", "/billing/verify"): "billing_lifecycle.py:billing_verify",
    ("POST", "/billing/razorpay/webhook"): "billing_lifecycle.py:razorpay_webhook",
    ("POST", "/projects/upload"): "secure_upload.py:upload_project",
    ("POST", "/clips/{clip_id}/export"): "worker_jobs.py:export_clip",
}
for route, expected_owner in canonical_routes.items():
    check(
        f"canonical route owner: {route[0]} {route[1]}",
        route_map.get(route) == [expected_owner],
        f"owners={route_map.get(route)} expected={[expected_owner]}",
    )

# --- Container assets / media dependencies --------------------------------
dockerfile = text("backend/Dockerfile")
check("runtime installs FFmpeg", "ffmpeg" in dockerfile)
check("runtime installs Tesseract OCR", "tesseract-ocr" in dockerfile)
check("runtime installs Noto font package", "fonts-noto-core" in dockerfile)
check("caption/OCR assets copied into image", "COPY assets ./assets" in dockerfile)

# --- Large upload spooling / edge bound -----------------------------------
compose = text("docker-compose.hostinger.yml")
caddy = text("Caddyfile")
database = text("backend/app/core/database.py")
config = text("backend/app/core/config.py")
check("storage-backed multipart TMPDIR configured", "TMPDIR: /app/storage/tmp" in compose)
check("storage temp directory is created", "settings.temp_dir.mkdir(parents=True, exist_ok=True)" in database)
check("settings exposes storage temp directory", 'return self.storage_root / "tmp"' in config)
check("Caddy bounds API request bodies", "request_body" in caddy and re.search(r"max_size\s+525MiB", caddy) is not None)
check("production Caddy image supports request_body", "image: caddy:2.10" in compose)

# --- Production fail-closed defaults --------------------------------------
prod = text(".env.production.example")
check("production domain is a placeholder", "DOMAIN=REPLACE_WITH_DOMAIN" in prod)
check("production frontend URL derives from placeholder", "FRONTEND_URL=https://REPLACE_WITH_DOMAIN" in prod)
check("production boot validates HTTPS frontend callback URL", "FRONTEND_URL_NOT_HTTPS" in text("backend/app/services/production_configuration.py"))
check("local LIVE Razorpay bypass disabled in production example", "ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT=false" in prod)
check("generic production Hinglish provider is legacy", "HINGLISH_ASR_PROVIDER=legacy" in prod)
check("generic Stage-1 rollout disabled", "HINGLISH_STAGE1_ENABLED=false" in prod)
check("generic Stage-1 allowlist empty", re.search(r"^HINGLISH_STAGE1_USER_IDS=\s*$", prod, re.M) is not None)
check("generic production API ASR enabled", "ASR_MODE=api" in prod)
check("generic production native timing policy", "ALIGNMENT_BACKEND=native" in prod and "REQUIRE_FORCED_ALIGNMENT=false" in prod)
check("no fake clipkaro.pro launch domain in production example", "clipkaro.pro" not in prod.lower())

# --- Email one-time-token safety ------------------------------------------
transactional = text("backend/app/services/transactional_email.py")
email_verification = text("backend/app/services/email_verification.py")
account_security = text("backend/app/services/account_security.py")
check("password reset uses shared transactional email", "send_transactional_email(_password_reset_message" in account_security)
check("verification uses shared transactional email", "send_transactional_email(_verification_message" in email_verification)
combined_email = transactional + email_verification + account_security
check("no legacy verification-link console marker", "[VERIFICATION LINK]" not in combined_email)
check("transactional fallback does not log message body", "message.text" not in re.sub(r"def _send_with_[\s\S]*?(?=async def send_transactional_email)", "", transactional))
check("verification links keep token in URL fragment", "/verify-email#token=" in email_verification)
check("password reset links keep token in URL fragment", "/reset-password#token=" in account_security)
check("Resend sender is never silently replaced with resend.dev", 'from_addr = "ClipKaro AI <onboarding@resend.dev>"' not in transactional)
check("production email preflight verifies Resend sender domain", "_probe_resend_domains_sync" in transactional and "sender_domain_unverified" in transactional and "sender_domain_verified" in transactional)
check("configured transactional email failures never report false success", "transactional_email_unfulfilled" not in transactional)

# --- Billing fail-closed / capture truth ----------------------------------
billing = text("backend/app/api/billing_lifecycle.py")
check("one-time callback fetches provider payment", 'razorpay_request("GET", f"/payments/{payment_id}")' in billing)
check("one-time entitlement requires captured provider truth", "identity_valid, captured = _provider_payment_matches_checkout" in billing and "if captured:" in billing)
check("authorized one-time payment remains pending", "status='authorized'" in billing)
check("webhook idempotency prefers Razorpay event id", 'X-Razorpay-Event-Id' in billing and "provider_event_id" in billing)
check("webhook id is atomically claimed before entitlement side effects", "_claim_webhook_event" in billing and "'processing'" in billing and "claim Razorpay webhook" in billing)
check("failed webhook reconciliation releases only unfinished claim", "_release_webhook_claim" in billing and "status='processing'" in billing)
check("stale webhook processing claims are crash-recoverable", "_WEBHOOK_PROCESSING_CLAIM_TTL_SECONDS" in billing and "claimed_at" in billing and "return \"claimed\"" in billing)
check("pre-charge subscription webhook cannot grant entitlement", "entitlement_evidence" in billing and "server-created checkout proves ownership, not payment" in billing)
check("browser subscription activation requires active provider state", 'activated = provider_status == "active"' in billing)
check("subscription checkout verified state follows actual local entitlement", "local_entitlement_active" in billing and "pending retry may carry paid_count" in billing)
check("verified checkout replay reports current entitlement truth", "A verified checkout is historical payment truth" in billing and '"activated": activated' in billing)
check("subscription pause/resume lifecycle is recognized", '"subscription.paused"' in billing and '"subscription.resumed"' in billing and 'status == "paused"' in billing)
check("expired paused subscription cannot retain paid access indefinitely", 'status in {"authenticated", "pending", "paused"}' in billing and "boundary <= utc_now()" in billing)
check("pending subscription plan cannot activate before active provider truth", 'return user\n\n    if status != "active"' in billing and "test_pending_subscription_plan_id_does_not_apply_plan_change_before_active_provider_truth" in text("backend/tests/test_subscription_lifecycle.py"))
check("subscription webhook reconciliation stays provider-network free", "allow_provider_followup=False" in billing and "test_subscription_webhook_does_not_block_on_provider_followup_api" in text("backend/tests/test_subscription_lifecycle.py"))
billing_service = text("backend/app/services/billing.py")
check("legacy subscription sync never trusts provider notes for entitlement", 'notes.get("plan")' not in billing_service and 'resolved_plan = str((expected or {}).get("plan_key") or plan)' in billing_service)
check("legacy subscription sync does not treat generic scheduled change as cancellation", 'cancel_at_period_end=bool(entity.get("has_scheduled_changes"))' not in billing_service)
check("browser subscription verification does not treat generic scheduled change as cancellation", 'cancel_at_period_end=bool(entity.get("has_scheduled_changes"))' not in billing)
check("webhook payload redacts payer fields", "_sanitize_webhook_payload" in billing and "[redacted]" in billing)
check("captured one-time webhook can recover entitlement", 'event_type in {"payment.captured", "order.paid"}' in billing and "_activate_one_time_checkout" in billing)
check("failed/authorized one-time webhooks never imply capture", 'event_type in {"payment.authorized", "payment.failed"}' in billing and "_one_time_payment_state_is_valid" in billing and "status!='verified'" in billing)
check("backend paid commitment requires current legal acceptance", "_require_new_paid_commitment_ready" in billing and "has_current_legal_acceptance" in billing)
check("downgrade/cancel path stays separate from paid-upgrade gate", "if is_upgrade:" in billing and "await _require_new_paid_commitment_ready" in billing)
pricing = text("frontend/app/pricing/page.tsx")
check("Razorpay script loader has bounded failure timeout", "12_000" in pricing and "took too long to load" in pricing and "razorpayLoadPromise = null" in pricing)
check("Razorpay frontend surfaces payment.failed without launching a second checkout", 'razorpay.on?.("payment.failed"' in pricing and "You can retry securely in Razorpay Checkout" in pricing)
check("checkout creation is serialized per user", "async with _checkout_locks[str(user[\"id\"])]" in billing)
check("fresh unfinished checkout is reused instead of duplicating provider commitments", "_recent_reusable_checkout" in billing and "billing.checkout_reused" in billing)

# --- Re-analysis durability / historical export safety --------------------
worker_jobs = text("backend/app/api/worker_jobs.py")
worker = text("backend/app/worker.py")
routes = text("backend/app/api/routes.py")
check("explicit language re-analysis persists force flag", '"force_transcribe": bool(force_transcribe)' in worker_jobs)
check("isolated worker replays force-transcribe intent", 'get("force_transcribe", False)' in worker and "force_transcribe" in worker)
check("forced retry can reuse transcript from same durable job", 'processing_job_id' in routes and "same_job_transcript" in routes)
check("re-analysis preserves exported historical clips", "status='superseded'" in routes and "EXISTS (SELECT 1 FROM exports e WHERE e.clip_id=clips.id)" in routes)
check("current project queries hide superseded clips", "status<>'superseded'" in worker_jobs and "status<>'superseded'" in routes)
check("re-analysis blocks while export is active", "Wait for the current export to finish before re-analysing" in worker_jobs)
check("re-analysis has bounded abuse guard", "MAX_REPROCESS_ATTEMPTS_PER_24H = 3" in worker_jobs)
check("expired source blocks new re-analysis/export", "source video has expired" in worker_jobs.lower() and "source_available" in worker_jobs)
check("automatic old-pipeline upgrade waits for active export", 'project["upgrade_blocked"] = "active_export"' in worker_jobs)
check("automatic export-triggered upgrade rejects expired source", "Upload it again to upgrade this project" in worker_jobs)
check("analytics avoids join-multiplying processed minutes", "SELECT COALESCE(SUM(v.duration),0) FROM videos v JOIN projects p" in routes)

# --- Brand Kit truthfulness ------------------------------------------------
editor = text("frontend/app/editor/[clipId]/page.tsx")
brand_page = text("frontend/app/brand/page.tsx")
rendering = text("backend/app/services/rendering.py")
check("Creator Studio sends selected Brand Kit to export", "brand_kit_id: brandKitId || null" in editor)
check("Creator Studio previews user brand separately", "canvas-brandmark" in editor and "selectedBrandKit?.logo_text" in editor)
check("Brand Kit UI exposes a real caption preset", 'name="preset"' in brand_page and 'caption_preset: d.get("preset")' in brand_page)
check("user wordmark renders independently of ClipKaro watermark", 'product_mark = "ClipKaro AI"' in rendering and "if safe_brand:" in rendering)

# --- Backend dependency security floors -----------------------------------
requirements = text("backend/requirements.txt")
candidate_requirements = text("backend/requirements-candidate-asr.txt")
check("production requirements exclude experimental NVIDIA Riva client", "nvidia-riva-client" not in requirements.lower())
check("candidate ASR profile retains optional NVIDIA Riva client", "nvidia-riva-client" in candidate_requirements.lower())
pyjwt_match = re.search(r"^PyJWT==([^\s#]+)", requirements, re.M)
pyjwt_version = pyjwt_match.group(1) if pyjwt_match else "0.0.0"
check(
    "PyJWT security floor >= 2.13.0",
    version_tuple(pyjwt_version) >= (2, 13, 0),
    f"pinned={pyjwt_version}",
)

fastapi_match = re.search(r"^fastapi==([^\s#]+)", requirements, re.M)
fastapi_version = fastapi_match.group(1) if fastapi_match else "0.0.0"
check(
    "FastAPI release floor >= 0.141.1",
    version_tuple(fastapi_version) >= (0, 141, 1),
    f"pinned={fastapi_version}",
)

starlette_match = re.search(r"^starlette==([^\s#]+)", requirements, re.M)
starlette_version = starlette_match.group(1) if starlette_match else "0.0.0"
check(
    "Starlette security floor >= 1.3.1",
    version_tuple(starlette_version) >= (1, 3, 1),
    f"pinned={starlette_version}",
)

python_multipart_match = re.search(r"^python-multipart==([^\s#]+)", requirements, re.M)
python_multipart_version = python_multipart_match.group(1) if python_multipart_match else "0.0.0"
check(
    "python-multipart security floor >= 0.0.31",
    version_tuple(python_multipart_version) >= (0, 0, 31),
    f"pinned={python_multipart_version}",
)

requests_match = re.search(r"^requests==([^\s#]+)", requirements, re.M)
requests_version = requests_match.group(1) if requests_match else "0.0.0"
check(
    "Requests security floor >= 2.32.4",
    version_tuple(requests_version) >= (2, 32, 4),
    f"pinned={requests_version}",
)

# --- Framework/runtime release versions -----------------------------------
frontend_dockerfile = text("frontend/Dockerfile")
check("frontend container uses supported Node 24 LTS", frontend_dockerfile.count("node:24-alpine") == 3)
package = json.loads(text("frontend/package.json"))
lock = json.loads(text("frontend/package-lock.json"))
check("Next 16 package scripts do not call removed next lint", "next lint" not in json.dumps(package.get("scripts", {})))
check("frontend exposes explicit TypeScript release check", package.get("scripts", {}).get("typecheck") == "tsc --noEmit")
next_declared = package.get("dependencies", {}).get("next", "0.0.0")
next_locked = lock.get("packages", {}).get("node_modules/next", {}).get("version", "0.0.0")
react_locked = lock.get("packages", {}).get("node_modules/react", {}).get("version", "0.0.0")
check("Next.js release floor >= 16.2.11", version_tuple(next_locked) >= (16, 2, 11), f"locked={next_locked}")
check("package.json/package-lock Next versions agree", version_tuple(next_declared) == version_tuple(next_locked), f"declared={next_declared} locked={next_locked}")
check("React locked version >= 19.2.7", version_tuple(react_locked) >= (19, 2, 7), f"locked={react_locked}")

# --- Release hygiene -------------------------------------------------------
check("demo user seeding defaults off in production compose", 'SEED_DEMO_USER: "false"' in compose)
check("production local LIVE Razorpay opt-in forced off", 'ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT: "false"' in compose)
check("worker consumes API ASR by default", "ASR_MODE: ${ASR_MODE:-api}" in compose)
check("worker image target matches explicit ASR runtime choice", "target: ${WORKER_IMAGE_TARGET:-api}" in compose and "WORKER_IMAGE_TARGET=api" in prod)
check("local WhisperX worker target is documented fail-explicit", "WORKER_IMAGE_TARGET=worker" in prod and "ASR_MODE=local" in prod)
prod_env_check = text("scripts/check-production-env.py")
check("offline production env check enforces live Razorpay mode and disables local opt-in", "RAZORPAY_MODE_NOT_LIVE" in prod_env_check and "LIVE_RAZORPAY_DEVELOPMENT_OPT_IN_ENABLED" in prod_env_check)
check("offline production env check enforces worker image/ASR mode pairing", "WORKER_IMAGE_TARGET_ASR_MODE_MISMATCH" in prod_env_check)
check("offline production env check binds public URLs to configured domain", "APP_PUBLIC_URL_DOMAIN_MISMATCH" not in prod_env_check and 'b.append(f"{key}_DOMAIN_MISMATCH")' in prod_env_check)
check("rate-limit maps prune inactive client keys", "_prune_rate_limit_buckets(current)" in main and "registry.pop(key, None)" in main)
check("request IDs are validated before response reflection", "_REQUEST_ID_RE" in main and "_request_id(request)" in main and "_apply_security_headers" in main)
check("early middleware denials retain security headers", main.count("return _apply_security_headers(") >= 5)
check("expired export bytes are denied before cleanup", "_export_is_expired(row)" in routes and 'headers={"Cache-Control": "private, no-store"}' in routes)
storage_paths = text("backend/app/services/storage_paths.py")
media_api = text("backend/app/api/media.py")
cleanup = text("backend/app/services/cleanup.py")
check("persisted media paths are confined to private storage roots", "candidate.relative_to(base)" in storage_paths and "confined_upload_path" in media_api and "confined_export_path" in routes)
check("restart recovery confines persisted export paths", "confined_export_path" in main and "export_path.is_file()" in main)
check("isolated worker confines persisted export outputs", "confined_export_path" in worker and "Export output path is outside ClipKaro storage" in worker)
check("retention cleanup refuses out-of-storage database paths", "Refused out-of-storage expired source deletion" in cleanup and "Refused out-of-storage expired export deletion" in cleanup)
public_errors = text("backend/app/services/public_errors.py")
check("persisted media failures use user-safe diagnostics", "safe_project_failure(exc)" in routes and "safe_export_failure(exc)" in routes and "server logs" in public_errors)
check("trusted edge supplies real client IP for rate limiting", "header_up X-ClipKaro-Client-IP {remote_host}" in caddy and "_rate_limit_client_key(request)" in main)
preflight = text("backend/app/services/production_preflight.py")
check("API ASR preflight does not require local Whisper", '"api_asr_mode"' in preflight and 'settings.normalized_asr_mode == "api"' in preflight)

# Every new-tab link must protect window.opener. Next/modern browsers often
# imply this for _blank, but an explicit rel keeps the release invariant clear.
blank_link_issues: list[str] = []
for frontend_file in sorted((ROOT / "frontend").rglob("*.tsx")):
    source = frontend_file.read_text(encoding="utf-8")
    for match in re.finditer(r"<(?:a|Link)\b[^>]*target=[{]?['\"]_blank['\"]}?[^>]*>", source, re.S):
        tag = match.group(0)
        if not re.search(r"rel=[{]?['\"]noopener noreferrer['\"]}?", tag):
            blank_link_issues.append(str(frontend_file.relative_to(ROOT)))
check("all new-tab frontend links explicitly isolate opener", not blank_link_issues, ", ".join(sorted(set(blank_link_issues))))
backup_script = text("scripts/backup-production.sh")
restore_script = text("scripts/restore-production.sh")
check("production backup uses SQLite online backup and validates integrity", "src.backup(dst)" in backup_script and "PRAGMA integrity_check" in backup_script and "PRAGMA foreign_key_check" in backup_script)
check("production restore is explicit, offline and integrity checked", "RESTORE_CONFIRM=RESTORE_CLIPKARO" in restore_script and "stop web api worker" in restore_script and "os.replace(staged, destination)" in restore_script and "PRAGMA foreign_key_check" in restore_script)

print(f"\nStatic release verification: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

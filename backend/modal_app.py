"""Modal production entrypoints for ClipKaro's no-VPS architecture.

Deploy from the backend directory with:
    modal deploy modal_app.py

Run production database migrations safely from any supported local OS with:
    modal run modal_app.py::migrate_database

The existing FastAPI application remains the public API. Heavy media work is a
separate autoscaling Modal Function and receives only a durable PostgreSQL JOB_ID.
"""
from __future__ import annotations

import asyncio
import subprocess

import modal

APP_NAME = "clipkaro-production"
SECRET_NAME = "clipkaro-production"
POST_KARO_SECRET_NAME = "clipkaro-post-karo"
SMART_LAYOUT_CANARY_SECRET_NAME = "clipkaro-smart-layout-v2-canary"

# Existing backend selectors remain compatibility gates for the validated
# no-VPS code path. Concrete providers are selected independently so the
# preserved GCP implementation and the Modal/B2 implementation can coexist.
RUNTIME_ENV = {
    "APP_ENV": "production",
    "DATABASE_BACKEND": "postgres",
    "STORAGE_BACKEND": "gcs",
    "JOB_BACKEND": "cloud_run_job",
    "OBJECT_STORAGE_PROVIDER": "s3",
    "JOB_EXECUTION_PROVIDER": "modal",
    "MODAL_APP_NAME": APP_NAME,
    "MODAL_MEDIA_FUNCTION": "run_media_job",
    # Legacy preflight still expects a non-empty cloud bucket compatibility
    # marker. The concrete storage provider remains S3 and is actively probed
    # below before the public API is returned.
    "GCS_BUCKET": "CLIPKAROBILLION",
    "FRONTEND_URL": "https://clipkaro.pro",
    "APP_PUBLIC_URL": "https://clipkaro.pro",
    "CORS_ORIGINS": "https://clipkaro.pro",
    "ASR_MODE": "api",
    "UPLOAD_SCAN_REQUIRED": "true",
    "CLAMAV_HOST": "local",
    "POSTGRES_POOL_MIN_SIZE": "0",
    "POSTGRES_POOL_MAX_SIZE": "4",
    "POSTGRES_STATEMENT_CACHE_SIZE": "0",
}

SOURCE_IGNORE = [
    ".env",
    ".env.*",
    "storage/**",
    "tests/**",
    "sample_data/**",
    "**/node_modules/**",
    "**/.hyperframes/**",
    "cartoon_engine/sample/**",
    "cartoon_engine/smoke-project/**",
    "**/__pycache__/**",
    "**/*.pyc",
]

api_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    # copy=True is required because workdir/env are additional image steps.
    # It also keeps production source immutable inside the deployed image.
    .add_local_dir(".", "/root/clipkaro", ignore=SOURCE_IGNORE, copy=True)
    .workdir("/root/clipkaro")
    .env(RUNTIME_ENV)
)

media_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "curl",
        "ca-certificates",
        "gnupg",
        "ffmpeg",
        "libass9",
        "tesseract-ocr",
        "fonts-noto-core",
        "fonts-noto-cjk",
        "fonts-noto-color-emoji",
        "fonts-liberation2",
        "fontconfig",
        "libnss3",
        "libnspr4",
        "libatk1.0-0",
        "libatk-bridge2.0-0",
        "libatspi2.0-0",
        "libcups2",
        "libdrm2",
        "libxkbcommon0",
        "libxcomposite1",
        "libxdamage1",
        "libxfixes3",
        "libxrandr2",
        "libgbm1",
        "libasound2",
        "libx11-xcb1",
        "libxss1",
        "libxtst6",
        "libgtk-3-0",
        "libpango-1.0-0",
        "libcairo2",
        "libfontconfig1",
        "libfreetype6",
        "libxshmfence1",
        "libvulkan1",
        "libatomic1",
        "clamav",
        "clamav-freshclam",
    )
    # Pin the same Node runtime as the container renderer. HyperFrames and its
    # headless browser are built into the image; jobs never install packages at runtime.
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
        "apt-get install -y nodejs",
        "node --version && npm --version",
        "freshclam --stdout",
    )
    .pip_install_from_requirements("requirements.txt")
    .pip_install("numpy==2.1.3", "opencv-python-headless==4.11.0.86")
    # copy=True is required because workdir/env are additional image steps.
    .add_local_dir(".", "/root/clipkaro", ignore=SOURCE_IGNORE, copy=True)
    .workdir("/root/clipkaro")
    .env({**RUNTIME_ENV, "HYPERFRAMES_CACHE_DIR": "/root/.cache/hyperframes"})
    .run_commands(
        "cd /root/clipkaro/cartoon_engine && npm ci --omit=dev --no-audit --no-fund && ./node_modules/.bin/hyperframes browser ensure",
        "shell=\"$(find /root/.cache/hyperframes -type f -name 'chrome-headless-shell' -perm /111 | head -n 1)\"; test -n \"$shell\"; printf '%s\\n' \"$shell\" > /etc/hyperframes-headless-shell-path",
    )
)

# Source is already included explicitly in both images. Disable Modal's default
# source automount so deployment contents stay deterministic and minimal.
app = modal.App(APP_NAME, include_source=False)
production_secret = modal.Secret.from_name(SECRET_NAME)
post_karo_secret = modal.Secret.from_name(POST_KARO_SECRET_NAME)
smart_layout_canary_secret = modal.Secret.from_name(SMART_LAYOUT_CANARY_SECRET_NAME)


@app.function(
    image=api_image,
    secrets=[production_secret, post_karo_secret, smart_layout_canary_secret],
    timeout=300,
    schedule=modal.Period(hours=6),
)
def cleanup_expired_uploads() -> int:
    """Remove expired, unconsumed private uploads without touching live jobs."""
    from app.services.upload_cleanup import sweep_expired_uploads

    return asyncio.run(sweep_expired_uploads())


@app.function(
    image=api_image,
    secrets=[production_secret],
    timeout=300,
)
def migrate_database() -> str:
    """Apply forward-only Alembic migrations using production secrets.

    This function exists so Windows operators can run migrations without
    `modal shell`, which Modal does not currently support on Windows. It does
    not print DATABASE_URL or any secret values.
    """
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd="/root/clipkaro",
        check=True,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    return output or "Alembic upgrade head completed successfully."


@app.function(
    image=api_image,
    secrets=[production_secret, post_karo_secret, smart_layout_canary_secret],
    timeout=300,
    max_containers=20,
    min_containers=0,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=40, target_inputs=20)
@modal.asgi_app()
def api():
    # Fail closed on a bad B2/S3 credential, endpoint, or bucket before exposing
    # the FastAPI app. This is an authenticated HEAD-bucket probe; no user media
    # is read, written or deleted.
    from app.services.storage import get_storage_provider

    if not asyncio.run(get_storage_provider().probe()):
        raise RuntimeError("Production object storage readiness check failed.")

    from app.main import app as fastapi_app

    return fastapi_app


@app.function(
    image=media_image,
    secrets=[production_secret, post_karo_secret, smart_layout_canary_secret],
    # Long paid sources (up to 240 min) require sequential, bounded ASR chunks.
    # The 1-hour worker timeout used for <=60-minute uploads was insufficient.
    # Per-FFmpeg and per-provider request limits remain independently bounded.
    timeout=7200,
    cpu=2.0,
    memory=4096,
    # Modal currently provides a 512 GiB default ephemeral-disk quota. ClipKaro
    # only needs scratch space for bounded media jobs, so do not request a custom
    # larger quota unless workload evidence proves it necessary.
    max_containers=20,
    min_containers=0,
    scaledown_window=15,
)
def run_media_job(job_id: str) -> int:
    from app.media_job import run_job

    execution_id = f"modal:{modal.current_function_call_id()}"
    return asyncio.run(
        run_job(
            job_id,
            execution_id=execution_id,
            worker_prefix="modal",
        )
    )


@app.function(image=media_image, timeout=180, cpu=2.0, memory=4096, min_containers=0)
def smart_layout_preflight() -> dict:
    """Read-only smoke test in the SAME image used by the production media worker."""
    import cv2
    import numpy
    from app.services.karo_smart_layouts import VALID_MODES
    from app.services.video import find_media_tool

    ffmpeg = find_media_tool("ffmpeg")
    ffprobe = find_media_tool("ffprobe")
    result = {
        "ready": bool(ffmpeg and ffprobe and not cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        ).empty()),
        "ffmpeg": bool(ffmpeg),
        "ffprobe": bool(ffprobe),
        "opencv": cv2.__version__,
        "numpy": numpy.__version__,
        "layouts": sorted(VALID_MODES),
    }
    if not result["ready"]:
        raise RuntimeError("Modal media image is missing Smart Layout dependencies")
    print("KARO_SMART_LAYOUT_PREFLIGHT:", result)
    return result


@app.function(image=media_image, timeout=600, cpu=2.0, memory=4096, min_containers=0)
def cartoon_engine_preflight() -> dict:
    """Build and render a tiny cartoon in the exact production media image."""
    import json
    import shutil
    from pathlib import Path

    engine = Path("/root/clipkaro/cartoon_engine")
    cli = engine / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    node = shutil.which("node")
    if not node or not cli.is_file():
        raise RuntimeError("Node.js or the HyperFrames CLI is missing from the production media image.")

    sample = subprocess.run(
        ["python", "smoke_render.py"],
        cwd=str(engine),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if sample.returncode != 0:
        raise RuntimeError("Cartoon smoke project creation failed: " + (sample.stderr or sample.stdout)[-4000:])

    project = engine / "smoke-project"
    check = subprocess.run(
        [node, str(cli), "check", "--json", str(project)],
        cwd=str(engine),
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    if check.returncode != 0:
        raise RuntimeError("HyperFrames project check failed: " + (check.stderr or check.stdout)[-4000:])
    raw_report = (check.stdout or check.stderr).strip()
    json_start = raw_report.rfind("\\n{")
    json_start = json_start + 1 if json_start >= 0 else raw_report.find("{")
    if json_start < 0:
        raise RuntimeError("HyperFrames did not return its JSON check report.")
    report = json.loads(raw_report[json_start:])
    if not report.get("ok") or report.get("lint", {}).get("warningCount", 0):
        raise RuntimeError("HyperFrames project check reported errors or warnings.")

    output = Path("/tmp/clipkaro-cartoon-smoke.mp4")
    render = subprocess.run(
        [node, str(cli), "render", "--quality", "draft", "--workers", "1", "--low-memory-mode",
         "-o", str(output), str(project)],
        cwd=str(engine),
        capture_output=True,
        text=True,
        timeout=480,
        check=False,
    )
    if render.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        raise RuntimeError("HyperFrames smoke render failed: " + (render.stderr or render.stdout)[-4000:])

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError("FFprobe could not validate the rendered cartoon.")
    result = {
        "ready": True,
        "node": subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip(),
        "hyperframes": subprocess.run([node, str(cli), "--version"], capture_output=True, text=True, timeout=30).stdout.strip(),
        "check_warnings": report.get("lint", {}).get("warningCount", 0),
        "render_bytes": output.stat().st_size,
        "render_seconds": float(probe.stdout.strip()),
    }
    print("CARTOON_ENGINE_PREFLIGHT:", result)
    return result


@app.function(image=api_image, secrets=[production_secret, post_karo_secret], timeout=180)
def cartoon_credentials_preflight() -> dict:
    """Read-only production-secret and storage preflight; never returns secret values."""
    from app.core.config import get_settings
    from app.services.cartoon_security import decrypt_provider_key, encrypt_provider_key
    from app.services.storage import get_storage_provider

    settings = get_settings()
    test_value = "clipkaro-cartoon-credential-preflight"
    encrypted = encrypt_provider_key(test_value)
    round_trip = decrypt_provider_key(encrypted) == test_value
    storage_ready = asyncio.run(get_storage_provider().probe())
    result = {
        "encryption_key_configured": bool(settings.post_karo_encryption_key.strip()),
        "credential_round_trip": round_trip,
        "database_backend": settings.normalized_database_backend,
        "storage_ready": bool(storage_ready),
        "job_execution_provider": __import__("os").environ.get("JOB_EXECUTION_PROVIDER", ""),
    }
    if not result["encryption_key_configured"] or not round_trip or not storage_ready:
        raise RuntimeError("Cartoon Studio production configuration preflight failed.")
    print("CARTOON_CREDENTIALS_PREFLIGHT:", result)
    return result

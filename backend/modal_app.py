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
INGESTION_SECRET_NAME = "clipkaro-ingestion-worker"

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
        "ffmpeg",
        "libass9",
        "tesseract-ocr",
        "fonts-noto-core",
        "fonts-liberation2",
        "clamav",
        "clamav-freshclam",
    )
    # Build an initial signature set into the immutable image. Runtime scanning
    # remains fail-closed if ClamAV cannot inspect an uploaded media object.
    .run_commands("freshclam --stdout")
    .pip_install_from_requirements("requirements.txt")
    # copy=True is required because workdir/env are additional image steps.
    .add_local_dir(".", "/root/clipkaro", ignore=SOURCE_IGNORE, copy=True)
    .workdir("/root/clipkaro")
    .env(RUNTIME_ENV)
)

# Source is already included explicitly in both images. Disable Modal's default
# source automount so deployment contents stay deterministic and minimal.
app = modal.App(APP_NAME, include_source=False)
production_secret = modal.Secret.from_name(SECRET_NAME)
ingestion_secret = modal.Secret.from_name(INGESTION_SECRET_NAME)


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
    secrets=[production_secret, ingestion_secret],
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
    secrets=[production_secret, ingestion_secret],
    timeout=3600,
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

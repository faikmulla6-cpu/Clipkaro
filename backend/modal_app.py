"""Modal production entrypoints for ClipKaro's no-VPS architecture.

Deploy from the backend directory with:
    modal deploy modal_app.py

The existing FastAPI application remains the public API. Heavy media work is a
separate autoscaling Modal Function and receives only a durable PostgreSQL JOB_ID.
"""
from __future__ import annotations

import asyncio

import modal

APP_NAME = "clipkaro-production"
SECRET_NAME = "clipkaro-production"

# Existing backend selectors remain compatibility gates for the validated
# no-VPS code path. Concrete providers are selected by the provider-neutral
# OBJECT_STORAGE_PROVIDER/JOB_EXECUTION_PROVIDER environment variables.
RUNTIME_ENV = {
    "APP_ENV": "production",
    "DATABASE_BACKEND": "postgres",
    "STORAGE_BACKEND": "gcs",
    "JOB_BACKEND": "cloud_run_job",
    "OBJECT_STORAGE_PROVIDER": "s3",
    "JOB_EXECUTION_PROVIDER": "modal",
    "MODAL_APP_NAME": APP_NAME,
    "MODAL_MEDIA_FUNCTION": "run_media_job",
    "MODAL_ENVIRONMENT": "main",
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
    .add_local_dir(".", "/root/clipkaro", ignore=SOURCE_IGNORE)
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
    # Production scanning is fail-closed. A deployment must not bake a media
    # image without an initial ClamAV signature database.
    .run_commands("freshclam --stdout")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(".", "/root/clipkaro", ignore=SOURCE_IGNORE)
    .workdir("/root/clipkaro")
    .env(RUNTIME_ENV)
)

app = modal.App(APP_NAME)
production_secret = modal.Secret.from_name(SECRET_NAME)


@app.function(
    image=api_image,
    secrets=[production_secret],
    timeout=300,
    max_containers=20,
    min_containers=0,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=40, target_inputs=20)
@modal.asgi_app()
def api():
    from app.main import app as fastapi_app
    return fastapi_app


@app.function(
    image=media_image,
    secrets=[production_secret],
    timeout=3600,
    cpu=2.0,
    memory=4096,
    ephemeral_disk=10240,
    max_containers=20,
    min_containers=0,
    scaledown_window=15,
)
def run_media_job(job_id: str) -> int:
    from app.media_job import run_job
    execution_id = f"modal:{modal.current_function_call_id()}"
    return asyncio.run(run_job(job_id, execution_id=execution_id, worker_prefix="modal"))

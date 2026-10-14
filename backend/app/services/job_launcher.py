from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol

from app.core.config import get_settings


class JobLaunchError(RuntimeError):
    pass


class JobLauncher(Protocol):
    async def launch(self, job_id: str) -> str | None: ...


def job_execution_provider_name() -> str:
    configured = os.environ.get("JOB_EXECUTION_PROVIDER", "").strip().lower()
    if configured:
        if configured not in {"cloud_run", "modal"}:
            raise RuntimeError("JOB_EXECUTION_PROVIDER must be 'cloud_run' or 'modal'.")
        return configured
    return "cloud_run" if get_settings().normalized_job_backend == "cloud_run_job" else "local"


class LocalJobLauncher:
    async def launch(self, job_id: str) -> str | None:
        return None


class CloudRunJobLauncher:
    async def launch(self, job_id: str) -> str | None:
        settings = get_settings()
        if not all((settings.gcp_project_id, settings.gcp_region, settings.cloud_run_media_job_name)):
            raise JobLaunchError("Cloud Run media job configuration is incomplete.")
        from google.cloud import run_v2
        name = (
            f"projects/{settings.gcp_project_id}/locations/{settings.gcp_region}/jobs/"
            f"{settings.cloud_run_media_job_name}"
        )
        request = {
            "name": name,
            "overrides": {
                "container_overrides": [{"env": [{"name": "JOB_ID", "value": job_id}]}],
                "task_count": 1,
            },
        }
        try:
            operation = await asyncio.wait_for(
                asyncio.to_thread(run_v2.JobsClient().run_job, request=request),
                timeout=max(1.0, float(settings.cloud_run_job_timeout_seconds)),
            )
        except Exception as exc:
            raise JobLaunchError("Cloud Run media job launch failed.") from exc
        return str(getattr(getattr(operation, "operation", None), "name", "") or "") or None


class ModalJobLauncher:
    """Spawn one durable Modal Function execution for a PostgreSQL job row."""

    async def launch(self, job_id: str) -> str | None:
        app_name = os.environ.get("MODAL_APP_NAME", "clipkaro-production").strip()
        function_name = os.environ.get("MODAL_MEDIA_FUNCTION", "run_media_job").strip()
        environment = os.environ.get("MODAL_ENVIRONMENT", "").strip() or None
        if not app_name or not function_name:
            raise JobLaunchError("Modal media function configuration is incomplete.")
        try:
            import modal
            function = modal.Function.from_name(
                app_name,
                function_name,
                environment_name=environment,
            )
            call = await function.spawn.aio(job_id)
            return str(getattr(call, "object_id", "") or "") or None
        except Exception as exc:
            raise JobLaunchError("Modal media function launch failed.") from exc


def get_job_launcher() -> JobLauncher:
    settings = get_settings()
    if settings.normalized_job_backend != "cloud_run_job":
        return LocalJobLauncher()
    provider = job_execution_provider_name()
    if provider == "modal":
        return ModalJobLauncher()
    return CloudRunJobLauncher()

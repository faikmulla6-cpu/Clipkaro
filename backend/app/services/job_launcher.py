from __future__ import annotations

import asyncio
from typing import Any, Protocol

from app.core.config import get_settings


class JobLaunchError(RuntimeError):
    pass


class JobLauncher(Protocol):
    async def launch(self, job_id: str) -> str | None: ...


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


def get_job_launcher() -> JobLauncher:
    return CloudRunJobLauncher() if get_settings().normalized_job_backend == "cloud_run_job" else LocalJobLauncher()

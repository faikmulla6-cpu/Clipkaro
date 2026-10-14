from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings
from app.services.production_configuration import production_boot_configuration_issues


def main() -> int:
    settings = get_settings()
    blockers = production_boot_configuration_issues()
    checks = {
        "app_env_production": settings.app_env == "production",
        "postgres_selected": settings.normalized_database_backend == "postgres",
        "database_url_present": bool(settings.database_url.strip()),
        "gcs_selected": settings.normalized_storage_backend == "gcs",
        "gcs_bucket_present": bool(settings.gcs_bucket.strip()),
        "cloud_run_job_selected": settings.normalized_job_backend == "cloud_run_job",
        "gcp_project_present": bool(settings.gcp_project_id.strip()),
        "gcp_region_present": bool(settings.gcp_region.strip()),
        "media_job_present": bool(settings.cloud_run_media_job_name.strip()),
        "frontend_locked": settings.frontend_url.rstrip("/") == "https://clipkaro.pro",
        "origins_locked": set(settings.allowed_origins) == {"https://clipkaro.pro"},
        "demo_seed_disabled": not settings.seed_demo_user,
        "local_backends_disabled": settings.production_serverless_mode,
    }
    payload = {"ready": not blockers and all(checks.values()), "checks": checks, "blocker_codes": blockers}
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("Secret values were not printed.")
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

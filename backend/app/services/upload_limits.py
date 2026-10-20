"""Source upload size policy. Minutes and AI Short credits stay independent."""
from app.core.config import get_settings

MB = 1024 * 1024
PART_BYTES = 64 * MB
MULTIPART_THRESHOLD = 100 * MB
UPLOAD_LIMIT_MB = {
    "free": 500,
    "mini_pass": 500,
    "creator": 1024,
    "growth": 2048,
    "pro": 4096,
    "agency": 4096,
}


def allowed_upload_mb(plan: str, *, cloud_multipart: bool) -> int:
    # Synchronous API uploads must remain small to avoid saturating the public
    # API and its Starlette request spool space.
    maximum = UPLOAD_LIMIT_MB.get(str(plan).lower(), 500)
    if not cloud_multipart:
        maximum = min(500, maximum)
    return min(int(get_settings().max_upload_mb), maximum)

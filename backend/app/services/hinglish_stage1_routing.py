"""Creation-time Stage-1 routing decisions for durable media jobs.

The allowlist is intentionally consulted only while an authenticated request
creates a job.  Workers consume this small, persisted decision and never read
the mutable allowlist, avoiding rollout TOCTOU behaviour across retries and
restarts.
"""
from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings


LEGACY_ROUTE = "legacy"
ELEVENLABS_ROMAN_ROUTE = "elevenlabs_roman"
LEGACY_STAGE = "legacy"
STAGE1_STAGE = "stage1"


def resolve_stage1_route(language_hint: str, authenticated_user_id: str | None, *, settings: Settings | None = None) -> dict[str, str]:
    """Resolve a route from trusted server-side identity exactly once."""
    active_settings = settings or get_settings()
    if active_settings.stage1_hinglish_eligible(language_hint, authenticated_user_id):
        return {"asr_route": ELEVENLABS_ROMAN_ROUTE, "hinglish_rollout_stage": STAGE1_STAGE}
    return {"asr_route": LEGACY_ROUTE, "hinglish_rollout_stage": LEGACY_STAGE}


def persisted_stage1_route(payload: Any) -> dict[str, str]:
    """Read an old or malformed payload fail-closed, without policy lookup."""
    if not isinstance(payload, dict):
        return {"asr_route": LEGACY_ROUTE, "hinglish_rollout_stage": LEGACY_STAGE}
    if payload.get("asr_route") == ELEVENLABS_ROMAN_ROUTE:
        return {"asr_route": ELEVENLABS_ROMAN_ROUTE, "hinglish_rollout_stage": STAGE1_STAGE}
    return {"asr_route": LEGACY_ROUTE, "hinglish_rollout_stage": LEGACY_STAGE}

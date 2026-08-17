from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.database import fetch_one
from app.services.auth import current_user, require_role
from app.services.behavioral_learning import (
    ALLOWED_CHANGED_FIELDS,
    ALLOWED_SURFACES,
    CLIENT_EVENT_TYPES,
    record_client_event,
    record_server_event,
)
from app.services.behavioral_reporting import learning_diagnostics

router = APIRouter()


class ClipBehaviorEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    client_event_id: str = Field(min_length=8, max_length=120)
    client_session_id: str | None = Field(default=None, max_length=100)
    surface: str = Field(default="project", max_length=20)
    changed_fields: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("event_type")
    @classmethod
    def valid_event_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in CLIENT_EVENT_TYPES:
            raise ValueError("Unsupported creator behavior event.")
        return normalized

    @field_validator("surface")
    @classmethod
    def valid_surface(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_SURFACES:
            raise ValueError("Unsupported behavior surface.")
        return normalized

    @field_validator("changed_fields")
    @classmethod
    def valid_changed_fields(cls, values: list[str]) -> list[str]:
        cleaned = sorted({str(value).strip() for value in values if str(value).strip()})
        invalid = [value for value in cleaned if value not in ALLOWED_CHANGED_FIELDS]
        if invalid:
            raise ValueError("Unsupported edited field.")
        return cleaned


@router.post("/clips/{clip_id}/behavior", status_code=202)
async def clip_behavior(
    clip_id: str,
    body: ClipBehaviorEventRequest,
    user: dict = Depends(current_user),
) -> dict:
    try:
        return await record_client_event(
            user_id=str(user["id"]),
            clip_id=clip_id,
            event_type=body.event_type,
            client_event_id=body.client_event_id,
            client_session_id=body.client_session_id,
            surface=body.surface,
            changed_fields=body.changed_fields,
        )
    except LookupError as exc:
        # Preserve resource privacy: another creator cannot determine that the
        # clip/suggestion exists by probing this telemetry endpoint.
        raise HTTPException(404, "Clip suggestion not found.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/exports/{export_id}/download-event", status_code=204)
async def record_download_event(export_id: str, user: dict = Depends(current_user)) -> Response:
    export = await fetch_one(
        "SELECT id,clip_id,status FROM exports WHERE id=? AND user_id=?",
        (export_id, user["id"]),
    )
    if not export or export["status"] != "ready":
        raise HTTPException(404, "Export is not ready or has expired.")
    await record_server_event("downloaded", export_id=export_id, clip_id=export["clip_id"])
    return Response(status_code=204)


@router.get("/admin/learning/summary")
async def admin_learning_summary(_: dict = Depends(require_role("admin"))) -> dict:
    return await learning_diagnostics()

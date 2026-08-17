from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.database import fetch_all, fetch_one
from app.services.auth import current_user
from app.services.legal import (
    LEGAL_VERSION,
    create_privacy_request,
    legal_status,
    public_legal_config,
    record_legal_acceptance,
)


router = APIRouter()


class LegalAcceptanceRequest(BaseModel):
    accepted: bool
    version: str = Field(min_length=8, max_length=40)

    @field_validator("accepted")
    @classmethod
    def must_accept(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("You must agree to the current legal documents before continuing.")
        return value


class PrivacyRequestBody(BaseModel):
    kind: str = Field(min_length=3, max_length=20)
    details: str = Field(default="", max_length=1000)

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"access", "correction", "deletion", "grievance"}:
            raise ValueError("Choose access, correction, deletion or grievance.")
        return normalized


@router.get("/legal/config")
async def legal_config() -> dict:
    """Public operator/grievance particulars used by the legal pages."""
    return public_legal_config()


@router.get("/legal/status")
async def get_legal_status(user: dict = Depends(current_user)) -> dict:
    return await legal_status(str(user["id"]))


@router.post("/legal/accept")
async def accept_legal_documents(
    body: LegalAcceptanceRequest,
    request: Request,
    user: dict = Depends(current_user),
) -> dict:
    if body.version != LEGAL_VERSION:
        raise HTTPException(
            409,
            "The legal documents changed. Refresh this page and review the latest Terms, Privacy Notice and Refund Policy.",
        )
    try:
        return await record_legal_acceptance(
            str(user["id"]),
            body.version,
            source="authenticated",
            user_agent=request.headers.get("User-Agent", ""),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/privacy/export")
async def export_personal_data(user: dict = Depends(current_user)) -> dict:
    """Return a machine-readable account export without server secrets/file paths."""
    user_id = str(user["id"])
    account = await fetch_one(
        """SELECT id,name,email,plan,role,onboarding_complete,created_at,updated_at,
           billing_reference,plan_started_at,plan_expires_at,cancel_at_period_end
           FROM users WHERE id=?""",
        (user_id,),
    )
    preferences = await fetch_one(
        "SELECT default_language,timezone,creator_category,created_at,updated_at FROM user_preferences WHERE user_id=?",
        (user_id,),
    )
    projects = await fetch_all(
        """SELECT id,title,description,status,progress,stage,language,category,error,created_at,updated_at
           FROM projects WHERE user_id=? ORDER BY created_at""",
        (user_id,),
    )
    videos = await fetch_all(
        """SELECT v.id,v.project_id,v.original_filename,v.duration,v.width,v.height,v.file_size,v.status,v.created_at,v.expires_at
           FROM videos v JOIN projects p ON p.id=v.project_id WHERE p.user_id=? ORDER BY v.created_at""",
        (user_id,),
    )
    transcripts = await fetch_all(
        """SELECT t.id,t.video_id,t.language,t.text,t.segments_json,t.created_at
           FROM transcripts t JOIN videos v ON v.id=t.video_id JOIN projects p ON p.id=v.project_id
           WHERE p.user_id=? ORDER BY t.created_at""",
        (user_id,),
    )
    clips = await fetch_all(
        """SELECT c.id,c.video_id,c.start_time,c.end_time,c.hook,c.title,c.reason,c.transcript_text,
           c.score,c.score_breakdown_json,c.platform,c.status,c.created_at,c.updated_at
           FROM clips c JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
           WHERE p.user_id=? ORDER BY c.created_at""",
        (user_id,),
    )
    exports = await fetch_all(
        """SELECT id,clip_id,resolution,aspect_ratio,caption_style,watermark,status,progress,error,created_at,expires_at
           FROM exports WHERE user_id=? ORDER BY created_at""",
        (user_id,),
    )
    usage = await fetch_all(
        "SELECT month,source_minutes,exports_used,exports_limit FROM usage WHERE user_id=? ORDER BY month",
        (user_id,),
    )
    billing = await fetch_all(
        """SELECT kind,plan,provider_reference,amount,status,payment_id,created_at,verified_at
           FROM billing_checkouts WHERE user_id=? ORDER BY created_at""",
        (user_id,),
    )
    payment_events = await fetch_all(
        """SELECT provider_event_id,event_type,plan,amount,status,created_at
           FROM payment_events WHERE user_id=? ORDER BY created_at""",
        (user_id,),
    )
    legal_acceptances = await fetch_all(
        "SELECT version,documents_json,source,user_agent,accepted_at FROM legal_acceptances WHERE user_id=? ORDER BY accepted_at",
        (user_id,),
    )
    privacy_requests = await fetch_all(
        "SELECT id,kind,status,details,created_at,updated_at FROM privacy_requests WHERE user_id=? ORDER BY created_at",
        (user_id,),
    )
    recommendation_generations = await fetch_all(
        """SELECT id,project_id,video_id,language,category,ranking_source,ranking_model,
           app_version,pipeline_version,clip_count,created_at
           FROM recommendation_generations WHERE user_id=? ORDER BY created_at""",
        (user_id,),
    )
    suggestion_snapshots = await fetch_all(
        """SELECT id,generation_id,clip_id,suggestion_rank,start_time,end_time,duration,score,
           score_breakdown_json,platform,ranking_source,ranking_model,language,category,
           app_version,pipeline_version,created_at
           FROM clip_suggestion_snapshots WHERE user_id=? ORDER BY created_at,suggestion_rank""",
        (user_id,),
    )
    behavior_events = await fetch_all(
        """SELECT id,generation_id,clip_id,event_type,source,client_session_id,context_json,created_at
           FROM clip_behavior_events WHERE user_id=? ORDER BY created_at""",
        (user_id,),
    )
    return {
        "export_version": LEGAL_VERSION,
        "account": account,
        "preferences": preferences,
        "projects": projects,
        "videos": videos,
        "transcripts": transcripts,
        "clips": clips,
        "exports": exports,
        "usage": usage,
        "billing": billing,
        "payment_events": payment_events,
        "legal_acceptances": legal_acceptances,
        "privacy_requests": privacy_requests,
        "behavioral_learning": {
            "recommendation_generations": recommendation_generations,
            "suggestion_snapshots": suggestion_snapshots,
            "events": behavior_events,
        },
        "excluded": [
            "password hashes and authentication secrets",
            "server-side media file paths",
            "internal security secrets",
            "third-party credentials",
        ],
    }


@router.get("/privacy/requests")
async def list_privacy_requests(user: dict = Depends(current_user)) -> dict:
    rows = await fetch_all(
        "SELECT id,kind,status,details,created_at,updated_at FROM privacy_requests WHERE user_id=? ORDER BY created_at DESC",
        (user["id"],),
    )
    return {"requests": rows}


@router.post("/privacy/requests", status_code=202)
async def submit_privacy_request(body: PrivacyRequestBody, user: dict = Depends(current_user)) -> dict:
    try:
        created = await create_privacy_request(str(user["id"]), body.kind, body.details)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    current_plan = str(user.get("plan") or "free")
    created["message"] = "Your privacy request has been recorded for review."
    created["requires_billing_action"] = bool(
        body.kind == "deletion" and current_plan in {"creator", "growth", "pro", "agency"}
    )
    if created["requires_billing_action"]:
        created["message"] += " Because a recurring subscription is active, cancel it in Plans & billing so account closure cannot leave future renewals behind."
    return created
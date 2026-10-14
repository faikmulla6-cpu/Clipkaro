from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.jobs import create_job, dispatch_job, utcnow
from app.services.post_karo import (
    PostKaroProviderError,
    ZernioClient,
    _expired,
    _post_response,
    decrypt_api_key,
    encrypt_api_key,
    fingerprint_api_key,
    mask_api_key,
    run_publication_job,
    sync_supported_accounts,
    validate_api_key_shape,
)

router = APIRouter(prefix="/post-karo", tags=["post-karo"])
POST_KARO_PLANS = {"free", "mini_pass", "creator", "growth", "pro", "agency"}
SUPPORTED = {"instagram", "youtube"}


def _zernio_profile_name(user_id: str) -> str:
    digest = hashlib.sha256(("clipkaro-post-karo:" + str(user_id)).encode("utf-8")).hexdigest()[:12]
    return "ClipKaro-" + digest


class ConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=10, max_length=180)


class DraftPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    instagram_enabled: bool | None = None
    instagram_caption: str | None = Field(default=None, max_length=2200)
    instagram_hashtags: list[str] | None = Field(default=None, max_length=30)
    youtube_enabled: bool | None = None
    youtube_title: str | None = Field(default=None, max_length=100)
    youtube_description: str | None = Field(default=None, max_length=5000)
    youtube_tags: list[str] | None = Field(default=None, max_length=30)
    youtube_visibility: Literal["public", "unlisted", "private"] | None = None
    scheduled_for: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("instagram_hashtags", "youtube_tags")
    @classmethod
    def clean_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = list(dict.fromkeys(str(value).strip()[:100] for value in values if str(value).strip()))
        if sum(len(item) for item in cleaned) > 500:
            raise ValueError("Tags are too long for a social post.")
        return cleaned

class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=32, max_length=40)
    mode: Literal["now", "schedule"] = "now"
    scheduled_for: str | None = Field(default=None, max_length=80)
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=80)

    @field_validator("request_id")
    @classmethod
    def valid_request_id(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError) as exc:
            raise ValueError("Publishing request id must be a UUID.") from exc


def _eligible(user: dict[str, Any]) -> bool:
    return (
        str(user.get("plan") or "").strip().lower() in POST_KARO_PLANS
        or user.get("role") == "admin"
        or bool(user.get("post_karo_access_override"))
    )


def _require_eligible(user: dict[str, Any]) -> None:
    if not _eligible(user):
        raise HTTPException(
            403,
            "Post Karo is available on every ClipKaro plan.",
        )


async def _audit(user_id: str, event: str, entity_type: str, entity_id: str, metadata: dict[str, Any] | None = None) -> None:
    await execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()), user_id, event, entity_type, entity_id,
            json.dumps(metadata or {}, separators=(",", ":"), ensure_ascii=False), utcnow(),
        ),
    )

def _account_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": row.get("platform"),
        "username": row.get("username") or "",
        "display_name": row.get("display_name") or row.get("username") or "",
        "connected": row.get("connection_status") == "connected" and bool(row.get("can_post")),
        "status": row.get("connection_status") or "disconnected",
        "last_synced_at": row.get("last_synced_at"),
    }


def _loads_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _draft_out(row: dict[str, Any], export: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "export_id": row["export_id"],
        "revision": int(row.get("revision") or 1),
        "instagram_enabled": bool(row.get("instagram_enabled")),
        "instagram_caption": row.get("instagram_caption") or "",
        "instagram_hashtags": _loads_list(row.get("instagram_hashtags")),
        "youtube_enabled": bool(row.get("youtube_enabled")),
        "youtube_title": row.get("youtube_title") or "",
        "youtube_description": row.get("youtube_description") or "",
        "youtube_tags": _loads_list(row.get("youtube_tags")),
        "youtube_visibility": row.get("youtube_visibility") or "public",
        "scheduled_for": row.get("scheduled_for"),
        "timezone": row.get("timezone") or "Asia/Kolkata",
        "updated_at": row.get("updated_at"),
    }
    if export:
        result["export"] = export
    return result

def _publication_out(row: dict[str, Any], job: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        snapshot = json.loads(str(row.get("snapshot_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        snapshot = {}
    try:
        platform_results = json.loads(str(row.get("platform_results_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        platform_results = []
    return {
        "id": row["id"],
        "export_id": row["export_id"],
        "draft_id": row["draft_id"],
        "draft_revision": row["draft_revision"],
        "request_id": row["request_id"],
        "job_id": row.get("job_id"),
        "mode": row["mode"],
        "status": row["status"],
        "scheduled_for": row.get("scheduled_for"),
        "provider_post_id": row.get("provider_post_id"),
        "platform_results": platform_results if isinstance(platform_results, list) else [],
        "snapshot": snapshot if isinstance(snapshot, dict) else {},
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "job": job,
    }


async def _connection(user_id: str) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM post_karo_connections WHERE user_id=?", (user_id,))

async def _accounts(user_id: str) -> list[dict[str, Any]]:
    return await fetch_all(
        "SELECT * FROM post_karo_accounts WHERE user_id=? ORDER BY platform",
        (user_id,),
    )


def _provider_error(exc: PostKaroProviderError) -> HTTPException:
    return HTTPException(exc.status_code, exc.public_message)


@router.get("/status")
async def post_karo_status(user: dict = Depends(current_user)) -> dict[str, Any]:
    connection = await _connection(str(user["id"]))
    accounts = await _accounts(str(user["id"]))
    ready = [row for row in accounts if row.get("connection_status") == "connected" and row.get("can_post")]
    return {
        "plan_eligible": _eligible(user),
        "required_plan": "free",
        "connection_active": bool(connection),
        "api_key_masked": (connection or {}).get("api_key_masked"),
        "profile_ready": bool((connection or {}).get("profile_id")),
        "accounts": [_account_out(row) for row in accounts],
        "ready": bool(connection and ready),
        "setup_step": 3 if connection and ready else 2 if connection else 1,
    }


@router.post("/connection/test")
async def test_connection(body: ConnectionRequest, user: dict = Depends(current_user)) -> dict[str, Any]:
    _require_eligible(user)
    try:
        api_key = validate_api_key_shape(body.api_key)
        client = ZernioClient(api_key)
        await client.validate()
        profile_id = await client.ensure_clipkaro_profile(_zernio_profile_name(str(user["id"])))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PostKaroProviderError as exc:
        raise _provider_error(exc) from exc

    timestamp = utcnow()
    existing = await _connection(str(user["id"]))
    await execute(
        """INSERT INTO post_karo_connections(
             user_id,api_key_ciphertext,api_key_masked,api_key_fingerprint,profile_id,
             validated_at,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
             api_key_ciphertext=excluded.api_key_ciphertext,
             api_key_masked=excluded.api_key_masked,
             api_key_fingerprint=excluded.api_key_fingerprint,
             profile_id=excluded.profile_id,validated_at=excluded.validated_at,
             updated_at=excluded.updated_at""",
        (
            user["id"], encrypt_api_key(api_key), mask_api_key(api_key), fingerprint_api_key(api_key),
            profile_id, timestamp, (existing or {}).get("created_at") or timestamp, timestamp,
        ),
    )

    try:
        accounts = await sync_supported_accounts(str(user["id"]), api_key, profile_id)
    except PostKaroProviderError as exc:
        # The API key and profile were already validated. Provider-side account
        # discovery failures must remain a controlled setup error, never a 500.
        raise _provider_error(exc) from exc
    await _audit(
        str(user["id"]), "post_karo.connection_validated", "user", str(user["id"]),
        {"profile_ready": True, "connected_platforms": [row["platform"] for row in accounts if row.get("can_post")]},
    )
    return {
        "connection_active": True,
        "api_key_masked": mask_api_key(api_key),
        "profile_ready": True,
        "accounts": [_account_out(row) for row in accounts],
    }


@router.delete("/connection", status_code=204)
async def delete_connection(user: dict = Depends(current_user)) -> Response:
    await execute("DELETE FROM post_karo_accounts WHERE user_id=?", (user["id"],))
    await execute("DELETE FROM post_karo_connections WHERE user_id=?", (user["id"],))
    await _audit(str(user["id"]), "post_karo.disconnected", "user", str(user["id"]))
    return Response(status_code=204)


@router.post("/connect/{platform}")
async def connect_platform(
    platform: str,
    return_export: str | None = None,
    user: dict = Depends(current_user),
) -> dict[str, str]:
    _require_eligible(user)
    platform = platform.strip().lower()
    if platform not in SUPPORTED:
        raise HTTPException(404, "This platform is not available in Post Karo yet.")
    connection = await _connection(str(user["id"]))
    if not connection:
        raise HTTPException(409, "Activate your SIMPLE connection first.")
    try:
        api_key = decrypt_api_key(str(connection["api_key_ciphertext"]))
        base = get_settings().frontend_url.strip().rstrip("/") + "/"
        query: dict[str, str] = {"platform": platform}
        if return_export:
            await _export_context(return_export, str(user["id"]))
            query["return_export"] = return_export
        redirect_url = urljoin(base, "post-karo/callback") + "?" + urlencode(query)
        auth_url = await ZernioClient(api_key).connect_url(
            platform, str(connection["profile_id"]), redirect_url,
        )
    except PostKaroProviderError as exc:
        raise _provider_error(exc) from exc
    return {"auth_url": auth_url, "platform": platform}


@router.post("/accounts/sync")
async def sync_accounts(user: dict = Depends(current_user)) -> dict[str, Any]:
    _require_eligible(user)
    connection = await _connection(str(user["id"]))
    if not connection:
        raise HTTPException(409, "Activate your SIMPLE connection first.")
    try:
        api_key = decrypt_api_key(str(connection["api_key_ciphertext"]))
        rows = await sync_supported_accounts(str(user["id"]), api_key, str(connection["profile_id"]))
    except PostKaroProviderError as exc:
        raise _provider_error(exc) from exc
    ready = [row for row in rows if row.get("connection_status") == "connected" and row.get("can_post")]
    return {"accounts": [_account_out(row) for row in rows], "ready": bool(ready)}

async def _export_context(export_id: str, user_id: str) -> dict[str, Any]:
    row = await fetch_one(
        """SELECT e.*,c.id clip_id,c.title clip_title,c.hook,
                  v.project_id,p.title project_title
           FROM exports e
           JOIN clips c ON c.id=e.clip_id
           JOIN videos v ON v.id=c.video_id
           JOIN projects p ON p.id=v.project_id
           WHERE e.id=? AND e.user_id=?""",
        (export_id, user_id),
    )
    if not row:
        raise HTTPException(404, "Finished Short not found.")
    if row.get("status") != "ready" or _expired(row.get("expires_at")):
        raise HTTPException(410, "This Short is not available for Post Karo. Export it again first.")
    return row


def _prefill_from_pack(pack_row: dict[str, Any] | None, clip_id: str) -> dict[str, Any]:
    if not pack_row:
        return {}
    try:
        payload = json.loads(str(pack_row.get("payload_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    clips = payload.get("clips") if isinstance(payload, dict) else []
    if not isinstance(clips, list):
        return {}
    return next(
        (item for item in clips if isinstance(item, dict) and str(item.get("clip_id")) == clip_id),
        {},
    )


@router.post("/drafts/from-export/{export_id}", status_code=201)
async def draft_from_export(export_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    _require_eligible(user)
    export = await _export_context(export_id, str(user["id"]))
    existing = await fetch_one(
        "SELECT * FROM post_karo_drafts WHERE user_id=? AND export_id=?",
        (user["id"], export_id),
    )
    public_export = {
        "id": export["id"],
        "clip_id": export["clip_id"],
        "title": export.get("clip_title") or "ClipKaro Short",
        "project_title": export.get("project_title") or "Project",
        "download_url": f"/api/v1/exports/{export_id}/download",
        "expires_at": export.get("expires_at"),
        "resolution": export.get("resolution"),
        "aspect_ratio": export.get("aspect_ratio"),
    }
    if existing:
        return _draft_out(existing, public_export)

    pack_row = await fetch_one(
        "SELECT payload_json FROM content_packs WHERE project_id=? AND status='ready'",
        (export["project_id"],),
    )
    prefill = _prefill_from_pack(pack_row, str(export["clip_id"]))
    instagram = prefill.get("instagram_reels") if isinstance(prefill.get("instagram_reels"), dict) else {}
    youtube = prefill.get("youtube_shorts") if isinstance(prefill.get("youtube_shorts"), dict) else {}
    titles = youtube.get("titles") if isinstance(youtube.get("titles"), list) else []
    accounts = await _accounts(str(user["id"]))
    ready = {
        str(row["platform"]) for row in accounts
        if row.get("connection_status") == "connected" and row.get("can_post")
    }
    prefs = await fetch_one("SELECT timezone FROM user_preferences WHERE user_id=?", (user["id"],))
    timestamp = utcnow()
    draft_id = str(uuid.uuid4())
    await execute(
        """INSERT INTO post_karo_drafts(
             id,user_id,export_id,revision,instagram_enabled,instagram_caption,instagram_hashtags,
             youtube_enabled,youtube_title,youtube_description,youtube_tags,youtube_visibility,
             scheduled_for,timezone,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            draft_id, user["id"], export_id, 1, int("instagram" in ready),
            str(instagram.get("caption") or "")[:2200],
            json.dumps(instagram.get("hashtags") or [], ensure_ascii=False),
            int("youtube" in ready),
            str((titles[0] if titles else export.get("clip_title")) or "ClipKaro Short")[:100],
            str(youtube.get("description") or "")[:5000],
            json.dumps(youtube.get("hashtags") or [], ensure_ascii=False),
            "public", None, (prefs or {}).get("timezone") or "Asia/Kolkata", timestamp, timestamp,
        ),
    )
    row = await fetch_one("SELECT * FROM post_karo_drafts WHERE id=?", (draft_id,))
    if not row:
        raise HTTPException(500, "Post Karo could not prepare this Short.")
    return _draft_out(row, public_export)


def _parse_schedule(value: str | None, timezone_name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(422, "Choose a future date and time before scheduling.")
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Choose a valid future date and time.") from exc
    try:
        creator_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Choose a supported publishing timezone.") from exc
    if when.tzinfo is None:
        # datetime-local values intentionally have no offset. Interpret them in
        # the creator's selected IANA timezone before comparing with UTC.
        check_when = when.replace(tzinfo=creator_zone).astimezone(timezone.utc)
    else:
        check_when = when.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    if check_when <= now_utc + timedelta(minutes=1):
        raise HTTPException(422, "Choose a time at least one minute in the future.")
    if check_when > now_utc + timedelta(days=6, hours=23):
        raise HTTPException(422, "Post Karo can safely schedule up to 6 days ahead right now.")
    return raw


def _draft_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "instagram_enabled": bool(row.get("instagram_enabled")),
        "instagram_caption": row.get("instagram_caption") or "",
        "instagram_hashtags": _loads_list(row.get("instagram_hashtags")),

        "youtube_enabled": bool(row.get("youtube_enabled")),
        "youtube_title": row.get("youtube_title") or "",
        "youtube_description": row.get("youtube_description") or "",
        "youtube_tags": _loads_list(row.get("youtube_tags")),
        "youtube_visibility": row.get("youtube_visibility") or "public",
        "timezone": row.get("timezone") or "Asia/Kolkata",
    }


def _validate_publish_snapshot(snapshot: dict[str, Any], accounts: list[dict[str, Any]]) -> None:
    connected = {
        str(row.get("platform")) for row in accounts
        if row.get("connection_status") == "connected" and row.get("can_post")
    }
    selected = []
    if snapshot.get("instagram_enabled"):
        selected.append("instagram")
    if snapshot.get("youtube_enabled"):
        selected.append("youtube")
    if not selected:
        raise HTTPException(422, "Choose Instagram, YouTube, or both before posting.")
    unavailable = [platform for platform in selected if platform not in connected]
    if unavailable:
        label = " and ".join(platform.title() for platform in unavailable)
        raise HTTPException(409, f"{label} needs to be connected before this Short can post.")
    if snapshot.get("youtube_enabled") and not str(snapshot.get("youtube_title") or "").strip():
        raise HTTPException(422, "Add a YouTube title before posting.")


@router.patch("/drafts/{draft_id}")
async def update_draft(

    draft_id: str,
    body: DraftPatchRequest,
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    _require_eligible(user)
    values = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    if "instagram_hashtags" in values:
        values["instagram_hashtags"] = json.dumps(values["instagram_hashtags"], ensure_ascii=False)
    if "youtube_tags" in values:
        values["youtube_tags"] = json.dumps(values["youtube_tags"], ensure_ascii=False)
    for key in ("instagram_enabled", "youtube_enabled"):
        if key in values:
            values[key] = int(bool(values[key]))
    timestamp = utcnow()

    async def save(db):
        cursor = await db.execute(
            "SELECT * FROM post_karo_drafts WHERE id=? AND user_id=?",
            (draft_id, user["id"]),
        )
        current = await cursor.fetchone()
        if not current:
            raise HTTPException(404, "Post Karo draft not found.")
        current = dict(current)
        revision = int(current.get("revision") or 1)
        if revision != body.expected_revision:
            raise HTTPException(409, "This Post Karo draft changed in another tab. Refresh before posting.")
        if values:
            columns = ",".join(f"{key}=?" for key in values)
            await db.execute(
                f"UPDATE post_karo_drafts SET {columns},revision=?,updated_at=? WHERE id=? AND user_id=?",
                tuple(values.values()) + (revision + 1, timestamp, draft_id, user["id"]),
            )

        cursor = await db.execute("SELECT * FROM post_karo_drafts WHERE id=?", (draft_id,))
        saved = await cursor.fetchone()
        return dict(saved) if saved else None

    row = await run_in_transaction(save, operation_name="save Post Karo draft")
    if not row:
        raise HTTPException(500, "Post Karo could not save this draft.")
    return _draft_out(row)


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    row = await fetch_one(
        "SELECT * FROM post_karo_drafts WHERE id=? AND user_id=?",
        (draft_id, user["id"]),
    )
    if not row:
        raise HTTPException(404, "Post Karo draft not found.")
    export = await _export_context(str(row["export_id"]), str(user["id"]))
    public_export = {
        "id": export["id"], "clip_id": export["clip_id"],
        "title": export.get("clip_title") or "ClipKaro Short",
        "project_title": export.get("project_title") or "Project",
        "download_url": f"/api/v1/exports/{export['id']}/download",
        "expires_at": export.get("expires_at"),
        "resolution": export.get("resolution"),
        "aspect_ratio": export.get("aspect_ratio"),
    }
    return _draft_out(row, public_export)


@router.post("/drafts/{draft_id}/publish", status_code=202)
async def publish_draft(

    draft_id: str,
    body: PublishRequest,
    tasks: BackgroundTasks,
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    _require_eligible(user)
    connection = await _connection(str(user["id"]))
    if not connection:
        raise HTTPException(409, "Set up Post Karo before publishing.")
    accounts = await _accounts(str(user["id"]))
    scheduled_for = None
    if body.mode == "schedule":
        scheduled_for = _parse_schedule(body.scheduled_for, body.timezone)

    existing = await fetch_one(
        "SELECT * FROM post_karo_publications WHERE user_id=? AND request_id=?",
        (user["id"], body.request_id),
    )
    if existing:
        job = await fetch_one("SELECT * FROM jobs WHERE id=?", (existing.get("job_id"),)) if existing.get("job_id") else None
        return _publication_out(existing, job)

    draft = await fetch_one(
        "SELECT * FROM post_karo_drafts WHERE id=? AND user_id=?",
        (draft_id, user["id"]),
    )
    if not draft:
        raise HTTPException(404, "Post Karo draft not found.")
    if int(draft.get("revision") or 1) != body.expected_revision:
        raise HTTPException(409, "Your latest edits are not saved yet. Save them before posting.")
    await _export_context(str(draft["export_id"]), str(user["id"]))
    snapshot = _draft_snapshot(draft)
    _validate_publish_snapshot(snapshot, accounts)

    snapshot["timezone"] = body.timezone
    snapshot["scheduled_for"] = scheduled_for
    previous = await fetch_one(
        "SELECT * FROM post_karo_publications WHERE draft_id=? AND draft_revision=?",
        (draft_id, body.expected_revision),
    )
    if previous:
        job = await fetch_one("SELECT * FROM jobs WHERE id=?", (previous.get("job_id"),)) if previous.get("job_id") else None
        return _publication_out(previous, job)

    publication_id = str(uuid.uuid4())
    timestamp = utcnow()
    await execute(
        """INSERT INTO post_karo_publications(
             id,user_id,export_id,draft_id,draft_revision,request_id,job_id,mode,status,
             snapshot_json,provider_post_id,platform_results_json,error,scheduled_for,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,NULL,?,'queued',?,NULL,'[]',NULL,?,?,?)""",
        (
            publication_id, user["id"], draft["export_id"], draft_id, body.expected_revision,
            body.request_id, body.mode,
            json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False),
            scheduled_for, timestamp, timestamp,
        ),
    )
    try:
        job_id = await create_job(
            str(user["id"]), "post_karo_publish",
            payload={"publication_id": publication_id},
        )
        await execute(
            "UPDATE post_karo_publications SET job_id=?,updated_at=? WHERE id=?",
            (job_id, utcnow(), publication_id),
        )
        await dispatch_job(tasks, run_publication_job, job_id, publication_id)

    except Exception as exc:
        message = "ClipKaro could not safely start Post Karo. Your Short was not changed."
        await execute(
            "UPDATE post_karo_publications SET status='failed',error=?,updated_at=? WHERE id=?",
            (message, utcnow(), publication_id),
        )
        raise HTTPException(503, message) from exc

    await _audit(
        str(user["id"]), "post_karo.publish_requested", "post_karo_publication", publication_id,
        {"mode": body.mode, "draft_revision": body.expected_revision},
    )
    row = await fetch_one("SELECT * FROM post_karo_publications WHERE id=?", (publication_id,))
    job = await fetch_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    return _publication_out(row, job)


@router.get("/publications")
async def list_publications(user: dict = Depends(current_user)) -> list[dict[str, Any]]:
    rows = await fetch_all(
        "SELECT * FROM post_karo_publications WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
        (user["id"],),
    )
    return [_publication_out(row) for row in rows]


@router.get("/publications/{publication_id}")
async def publication_status(
    publication_id: str,
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    row = await fetch_one(
        "SELECT * FROM post_karo_publications WHERE id=? AND user_id=?",
        (publication_id, user["id"]),
    )

    if not row:
        raise HTTPException(404, "Post Karo publication not found.")

    # Immediate video publishes can remain in Zernio's publishing state while
    # Instagram or YouTube finish processing. Reconcile only this creator's
    # exact provider post instead of guessing success from the local job.
    if row.get("status") == "processing" and row.get("provider_post_id"):
        connection = await _connection(str(user["id"]))
        if connection:
            try:
                api_key = decrypt_api_key(str(connection["api_key_ciphertext"]))
                provider_payload = await ZernioClient(api_key).get_post(str(row["provider_post_id"]))
                provider_status, provider_post_id, results = _post_response(provider_payload)
                next_status = provider_status if provider_status in {"published", "partial", "failed", "scheduled"} else "processing"
                await execute(
                    """UPDATE post_karo_publications
                       SET status=?,provider_post_id=?,platform_results_json=?,error=?,updated_at=?
                       WHERE id=? AND user_id=?""",
                    (
                        next_status,
                        provider_post_id or row.get("provider_post_id"),
                        json.dumps(results, separators=(",", ":"), ensure_ascii=False),
                        "One or more selected platforms could not publish this Short." if next_status in {"partial", "failed"} else None,
                        utcnow(),
                        publication_id,
                        user["id"],
                    ),
                )
                row = await fetch_one(
                    "SELECT * FROM post_karo_publications WHERE id=? AND user_id=?",
                    (publication_id, user["id"]),
                )
            except PostKaroProviderError:
                # A transient status-read failure must not overwrite an already
                # accepted publish. The browser can retry this read safely.
                pass

    job = await fetch_one("SELECT * FROM jobs WHERE id=?", (row.get("job_id"),)) if row.get("job_id") else None
    return _publication_out(row, job)

from __future__ import annotations

import json
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.database import POSTGRES_PREVIOUS_SCHEMA_REVISION, POSTGRES_SCHEMA_REVISION, execute, fetch_all, fetch_one, run_in_transaction
from app.services.distributed_rate_limit import consume_rate_limit
from app.services.auth import current_user
from app.services.cartoon_speech import SYSTEM_URDU_TTS_MODEL, built_in_voice_models, built_in_voice_selection
from app.services.cartoon_story import resolve_cartoon_language
from app.services.cartoon_story_render import saved_caption_timeline
from app.services.cartoon_usage import cartoon_balance, claim_cartoon_refill, reserve_cartoon_period, usage_schema_ready
from app.services.cartoon_story_planner import (
    NVIDIA_STORY_MODEL, OPENROUTER_ROOT, PROJECT_STORY_MODELS, STORY_MODEL, StoryboardReplyError,
    parse_storyboard_reply, planner_payload, request_storyboard, storyboard_correction_payload,
)
from app.services.cartoon_security import (
    CartoonCredentialError, decrypt_provider_key, encrypt_provider_key,
    fingerprint_provider_key, mask_provider_key,
)
from app.services.jobs import create_job, dispatch_job, event_payload, update_job, utcnow
from app.services.storage import (
    get_storage_provider, object_storage_provider_name, validate_object_key,
)
from app.services.video import save_upload

router = APIRouter(prefix="/cartoon-studio", tags=["cartoon-studio"])


async def _run_media_job(job_id: str) -> int:
    # Cloud Run dispatch never imports the full media pipeline in the API process.
    # Local background mode imports it only when the queued task actually runs.
    from app.media_job import run_job

    return await run_job(job_id)


ALLOWED_DURATIONS = {15, 30, 45, 60}
ALLOWED_RATIOS = {"9:16", "16:9", "1:1", "4:5"}
ALLOWED_STYLES = {"2d-cartoon", "storybook", "anime-inspired", "flat-vector", "cinematic-jannat"}
ALLOWED_LANGUAGES = {"auto", "en", "hi", "hinglish", "mr", "ur"}


def _storyboard_test_allowed(user: dict) -> bool:
    allowed = get_settings().cartoon_storyboard_test_user_ids.split(",")
    return str(user["id"]) in {value.strip() for value in allowed if value.strip()}


def _validate_nvidia_key(api_key: str) -> str:
    key = api_key.strip()
    if not re.fullmatch(r"nvapi-[A-Za-z0-9_-]{14,480}", key):
        raise HTTPException(422, "Enter an NVIDIA API key beginning with nvapi-.")
    return key


@router.get("/capabilities")
async def cartoon_capabilities(user: dict = Depends(current_user)) -> dict:
    return {"engine_version": "story-v3", "storyboard_version": 3, "aspect_ratios": ["9:16", "16:9", "1:1", "4:5"]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _provider_key(user_id: str, provider: str = "openrouter") -> str | None:
    row = await fetch_one(
        "SELECT api_key_ciphertext FROM cartoon_provider_credentials WHERE user_id=? AND provider=?",
        (user_id, provider),
    )
    if not row:
        return None
    try:
        return decrypt_provider_key(str(row["api_key_ciphertext"]))
    except CartoonCredentialError as exc:
        label = "NVIDIA" if provider == "nvidia" else "OpenRouter"
        raise HTTPException(409, f"Reconnect your {label} API key securely before continuing.") from exc


async def _nvidia_key_for_request(user: dict, supplied: str) -> str:
    # Keep request-only credentials confined to the existing internal test flow.
    if supplied.strip():
        if not _storyboard_test_allowed(user):
            raise HTTPException(403, "Save your NVIDIA API key in API Keys & Advanced Settings.")
        return _validate_nvidia_key(supplied)
    key = await _provider_key(user["id"], "nvidia")
    if not key:
        raise HTTPException(409, "Save your NVIDIA API key in API keys before continuing.")
    return key


async def _models(api_key: str, modality: str) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0)) as client:
            response = await client.get(
                f"{OPENROUTER_ROOT}/models",
                params={"output_modalities": modality},
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Could not reach OpenRouter. Check your connection and retry.") from exc
    if response.status_code == 401:
        raise HTTPException(401, "OpenRouter rejected this API key. Check the key and reconnect.")
    if response.status_code == 403:
        raise HTTPException(403, "OpenRouter denied this API key. Check its account permissions.")
    if response.status_code == 429:
        raise HTTPException(429, "OpenRouter rate-limited the key check. Wait a moment and retry.")
    if response.status_code >= 500:
        raise HTTPException(503, "OpenRouter is temporarily unavailable.")
    if response.status_code >= 400:
        raise HTTPException(400, "OpenRouter could not validate this request.")
    try:
        data = response.json().get("data", [])
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(502, "OpenRouter returned an unreadable model list.")


def _project_out(
    row: dict[str, Any], job: dict[str, Any] | None = None, *, include_timeline: bool = False,
) -> dict[str, Any]:
    try:
        storyboard = json.loads(str(row.get("storyboard_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        storyboard = {}

    try:
        assets = json.loads(str(row.get("assets_json") or "{}"))
        if not isinstance(assets, dict):
            assets = {}
    except (ValueError, TypeError):
        assets = {}
    job = job or {}
    job_status = str(job.get("status") or row.get("job_status") or "")
    project_status = str(row.get("status") or "queued")
    status = "ready" if project_status == "ready" else (job_status or project_status)
    progress = job.get("progress", row.get("job_progress", row.get("progress", 0)))
    stage = job.get("stage") or row.get("job_stage") or row.get("stage") or "queued"
    message = job.get("message") or row.get("job_message")
    error = row.get("error") or (message if status == "failed" else None)

    result = {
        "id": row["id"],
        "job_id": row.get("job_id"),
        "title": row.get("title") or "Cartoon story",
        "prompt": row.get("prompt") or "",
        "duration_seconds": int(row.get("duration_seconds") or 30),
        "aspect_ratio": row.get("aspect_ratio") or "9:16",
        "style": row.get("style") or "2d-cartoon",
        "language": row.get("language") or "auto",
        "text_model": row.get("text_model") or STORY_MODEL,
        "status": status,
        "progress": max(0, min(100, int(progress or 0))),
        "stage": stage,
        "error": error,
        "storyboard": storyboard if isinstance(storyboard, dict) else {},
        "line_timed_captions": assets.get("_line_timed_captions") is True,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    if include_timeline and status == "ready":
        timeline = assets.get("_caption_timeline")
        result["caption_timeline"] = timeline if isinstance(timeline, list) else saved_caption_timeline(
            result["storyboard"], assets, duration=result["duration_seconds"],
            language=resolve_cartoon_language(result["language"], result["prompt"]),
        )
    return result


async def _owned_project(project_id: str, user_id: str) -> dict[str, Any]:
    row = await fetch_one("SELECT * FROM cartoon_projects WHERE id=? AND user_id=?", (project_id, user_id))
    if not row:
        raise HTTPException(404, "Cartoon project not found.")
    return row


async def _provider_status(user_id: str, provider: str) -> dict[str, Any]:
    row = await fetch_one(
        "SELECT api_key_masked,validated_at FROM cartoon_provider_credentials WHERE user_id=? AND provider=?",
        (user_id, provider),
    )
    return {
        "connected": bool(row),
        "masked_key": row.get("api_key_masked") if row else "",
        "validated_at": row.get("validated_at") if row and provider == "openrouter" else None,
    }


async def _nvidia_storage_ready() -> bool:
    if get_settings().normalized_database_backend != "postgres":
        return True
    row = await fetch_one("SELECT version_num FROM alembic_version LIMIT 1")
    return bool(row and row["version_num"] in {POSTGRES_SCHEMA_REVISION, POSTGRES_PREVIOUS_SCHEMA_REVISION})


@router.get("/providers")
async def get_providers(response: Response, user: dict = Depends(current_user)) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    status = {
        "storyboard_test_enabled": _storyboard_test_allowed(user),
        "openrouter": await _provider_status(user["id"], "openrouter"),
    }
    if await _nvidia_storage_ready():
        status["nvidia"] = await _provider_status(user["id"], "nvidia")
    return status


@router.post("/storyboard-test")
async def test_storyboard(
    response: Response,
    prompt: str = Form(""),
    duration_seconds: str = Form("30"),
    language: str = Form("auto"),
    style: str = Form("2d-cartoon"),
    provider: str = Form("openrouter"),
    nvidia_key: str = Form(""),
    user: dict = Depends(current_user),
) -> dict:
    if not _storyboard_test_allowed(user):
        raise HTTPException(403, "Storyboard testing is not enabled for this account.")
    response.headers["Cache-Control"] = "no-store"
    prompt = " ".join(prompt.split())
    if not 8 <= len(prompt) <= 3000:
        raise HTTPException(422, "Describe your cartoon in 8 to 3,000 characters.")
    if duration_seconds not in {str(duration) for duration in ALLOWED_DURATIONS}:
        raise HTTPException(422, "Choose a duration of 15, 30, 45 or 60 seconds.")
    if language not in ALLOWED_LANGUAGES or style not in ALLOWED_STYLES:
        raise HTTPException(422, "Choose a supported story language and style.")
    if provider not in {"nvidia", "openrouter"}:
        raise HTTPException(422, "Choose NVIDIA Nemotron or OpenRouter GLM.")
    if provider == "nvidia":
        key = await _nvidia_key_for_request(user, nvidia_key)
    else:
        key = await _provider_key(user["id"])
        if not key:
            raise HTTPException(409, "Connect your OpenRouter API key first.")
    if not await consume_rate_limit(str(user["id"]), group="cartoon_storyboard_test", limit=12, window_seconds=3600):
        raise HTTPException(429, "You have reached the storyboard testing limit. Try again later.")
    duration = int(duration_seconds)
    storyboard = await _plan_in_request(key, prompt, duration, style, resolve_cartoon_language(language, prompt), provider)
    return {"provider": provider, "model": NVIDIA_STORY_MODEL if provider == "nvidia" else STORY_MODEL,
            "storyboard": storyboard}


async def _request_plan(key: str, payload: dict, provider: str, timeout: int) -> httpx.Response:
    label = "NVIDIA" if provider == "nvidia" else "OpenRouter"
    try:
        upstream = await request_storyboard(key, payload, provider=provider, timeout=timeout)
    except (httpx.HTTPError, TimeoutError) as exc:
        raise HTTPException(504, f"{label} did not complete the storyboard. Try again shortly.") from exc
    if upstream.status_code in {401, 403}:
        raise HTTPException(422, f"{label} rejected the key or denied access to this model.")
    if upstream.status_code in {402, 429}:
        raise HTTPException(upstream.status_code, f"{label} reached an account credit or rate limit.")
    if upstream.status_code == 202:
        raise HTTPException(503, f"{label} did not finish the storyboard within this request. Try again shortly.")
    if not upstream.is_success:
        raise HTTPException(502, f"{label} could not complete the storyboard.")
    return upstream


async def _plan_in_request(
    key: str, prompt: str, duration: int, style: str, language: str, provider: str, *, repair_timing: bool = False,
) -> dict:
    payload = planner_payload(prompt, duration, style, language, provider=provider)
    upstream = await _request_plan(key, payload, provider, 65 if repair_timing else 105)
    try:
        return parse_storyboard_reply(upstream, prompt=prompt, duration=duration)
    except StoryboardReplyError as exc:
        if not repair_timing or exc.category != "CARTOON_STORY_BEAT_TIMING":
            raise HTTPException(502, str(exc)) from exc

    upstream = await _request_plan(key, storyboard_correction_payload(payload, "CARTOON_STORY_BEAT_TIMING"), provider, 40)
    try:
        return parse_storyboard_reply(upstream, prompt=prompt, duration=duration)
    except StoryboardReplyError as exc:
        message = ("NVIDIA still returned the wrong number of scenes after a correction attempt. "
                   "No video was queued. You can retry with the same script.")
        raise HTTPException(502, message if exc.category == "CARTOON_STORY_BEAT_TIMING" else str(exc)) from exc


async def _read_provider_key(request: Request, provider_label: str) -> str:
    # Framework validation errors can include the submitted value.
    error = f"Enter a valid {provider_label} API key."
    try:
        body = await request.json()
    except (ValueError, UnicodeError):
        raise HTTPException(422, error) from None
    if not isinstance(body, dict) or body.keys() != {"api_key"} or not isinstance(body["api_key"], str):
        raise HTTPException(422, error)
    return body["api_key"]


@router.post("/providers/openrouter")
async def save_openrouter_key(request: Request, user: dict = Depends(current_user)) -> dict[str, Any]:
    supplied_key = await _read_provider_key(request, "OpenRouter")
    key = supplied_key.strip()
    if not 20 <= len(supplied_key) <= 500 or not key.startswith("sk-or-"):
        raise HTTPException(422, "Enter a valid OpenRouter API key.")
    # Validate the key without making a billable generation request.
    await _models(key, "text")
    return await _save_provider_key(user["id"], "openrouter", key)


@router.post("/providers/nvidia")
async def save_nvidia_key(request: Request, response: Response, user: dict = Depends(current_user)) -> dict:
    if not await _nvidia_storage_ready():
        raise HTTPException(503, "NVIDIA key setup is temporarily unavailable. Try again shortly.")
    response.headers["Cache-Control"] = "no-store"
    # NVIDIA's public catalog cannot verify credentials without inference.
    key = _validate_nvidia_key(await _read_provider_key(request, "NVIDIA"))
    return await _save_provider_key(user["id"], "nvidia", key)


async def _save_provider_key(user_id: str, provider: str, key: str) -> dict[str, Any]:
    try:
        encrypted_key = encrypt_provider_key(key)
    except CartoonCredentialError as exc:
        raise HTTPException(503, "Secure provider-key storage is not configured. Please contact support.") from exc
    timestamp = _now()
    await execute(
        """INSERT INTO cartoon_provider_credentials(
             user_id,provider,api_key_ciphertext,api_key_masked,api_key_fingerprint,
             validated_at,created_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id,provider) DO UPDATE SET
             api_key_ciphertext=excluded.api_key_ciphertext,
             api_key_masked=excluded.api_key_masked,
             api_key_fingerprint=excluded.api_key_fingerprint,
             validated_at=excluded.validated_at,updated_at=excluded.updated_at""",
        (
            user_id, provider, encrypted_key, mask_provider_key(key),
            fingerprint_provider_key(key), timestamp, timestamp, timestamp,
        ),
    )
    return {
        "connected": True, "masked_key": mask_provider_key(key),
        "validated_at": timestamp if provider == "openrouter" else None,
    }


@router.delete("/providers/openrouter", status_code=204)
async def delete_openrouter_key(user: dict = Depends(current_user)) -> None:
    await execute(
        "DELETE FROM cartoon_provider_credentials WHERE user_id=? AND provider='openrouter'",
        (user["id"],),
    )


@router.delete("/providers/nvidia", status_code=204)
async def delete_nvidia_key(user: dict = Depends(current_user)) -> None:
    await execute(
        "DELETE FROM cartoon_provider_credentials WHERE user_id=? AND provider='nvidia'",
        (user["id"],),
    )


@router.get("/tts-models")
async def list_tts_models(user: dict = Depends(current_user)) -> dict[str, Any]:
    models = [
        {**item, "voices": item.get("supported_voices", [])}
        for item in built_in_voice_models()
    ]
    return {"models": models, "default_model": models[0]["id"]}


@router.get("/usage")
async def get_cartoon_usage(response: Response, user: dict = Depends(current_user)) -> dict | None:
    response.headers["Cache-Control"] = "no-store"
    return await cartoon_balance(str(user["id"])) if await usage_schema_ready() else None


@router.post("/usage/refill")
async def refill_cartoon_usage(response: Response, user: dict = Depends(current_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if not await usage_schema_ready():
        raise HTTPException(503, "Cartoon refills are temporarily unavailable.")
    return await claim_cartoon_refill(str(user["id"]))


@router.post("/projects")
async def create_cartoon_project(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    duration_seconds: int = Form(30),
    aspect_ratio: str = Form("9:16"),
    style: str = Form("2d-cartoon"),
    language: str = Form("auto"),
    tts_model: str = Form(""),
    voice_id: str = Form(""),
    story_planner: str = Form("glm"),
    nvidia_key: str = Form(""),
    reference_video: UploadFile | None = File(default=None),
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    prompt = " ".join(prompt.split()).strip()
    if not 8 <= len(prompt) <= 3000:
        raise HTTPException(422, "Describe your cartoon in 8 to 3,000 characters.")
    if duration_seconds not in ALLOWED_DURATIONS:
        raise HTTPException(422, "Choose a duration of 15, 30, 45 or 60 seconds.")
    if aspect_ratio not in ALLOWED_RATIOS:
        raise HTTPException(422, "Choose 9:16, 16:9, 1:1 or 4:5.")
    if style not in ALLOWED_STYLES:
        raise HTTPException(422, "Choose a supported cartoon style.")
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(422, "Choose a supported story language.")
    if story_planner not in PROJECT_STORY_MODELS:
        raise HTTPException(422, "Choose a supported story planner.")
    trial_key = None
    if story_planner == "nvidia":
        trial_key = await _nvidia_key_for_request(user, nvidia_key)
        if reference_video is not None and nvidia_key.strip():
            raise HTTPException(422, "Connect your NVIDIA API key in API Keys before adding a reference video.")
    requested_language = language
    language = resolve_cartoon_language(language, prompt)
    if story_planner != "nvidia" and not await _provider_key(user["id"]):
        raise HTTPException(409, "Add your OpenRouter API key before creating a cartoon.")
    active = await fetch_one(
        "SELECT id FROM cartoon_projects WHERE user_id=? AND status IN ('queued','processing') LIMIT 1",
        (user["id"],),
    )
    if active:
        raise HTTPException(409, "You already have a cartoon rendering. Wait for it to finish before starting another.")
    metered = await usage_schema_ready()
    if metered and duration_seconds > (await cartoon_balance(str(user["id"])))["remaining_seconds"]:
        raise HTTPException(409, "This duration exceeds your available cartoon time. Choose a shorter duration or check your refill.")
    compatible_tts_model = built_in_voice_selection(tts_model, language)
    if requested_language != language or (tts_model and tts_model != compatible_tts_model):
        voice_id = ""
    tts_model = compatible_tts_model
    selected_model = next((item for item in built_in_voice_models() if item["id"] == tts_model), None)
    if not selected_model or language not in selected_model["languages"]:
        raise HTTPException(422, "Choose a built-in voice for the story language.")

    if style == "cinematic-jannat" and (
        language != "ur" or tts_model != SYSTEM_URDU_TTS_MODEL
    ):
        raise HTTPException(
            422,
            "The Jannat story preset uses Urdu with the built-in Urdu voice.",
        )

    voice_choices = selected_model.get("voices_by_language", {}).get(language, selected_model.get("supported_voices", []))
    if voice_id and voice_id not in voice_choices:
        raise HTTPException(422, "Choose a voice supported by the selected speech model.")
    # Saved-key planning belongs in the worker. Only old preview forms using
    # a request-only key must finish planning before queueing.
    storyboard = {}
    if trial_key and nvidia_key.strip():
        storyboard = await _plan_in_request(
            trial_key, prompt, duration_seconds, style, language, "nvidia", repair_timing=True,
        )
    project_id = str(uuid.uuid4())
    timestamp = _now()
    title = prompt[:64].strip()
    reference_key = None
    reference_generation = None
    if reference_video is not None:
        settings = get_settings()
        suffix = Path(reference_video.filename or "").suffix.lower()
        temp_path = settings.storage_root / "tmp" / f"cartoon-reference-{uuid.uuid4().hex}{suffix}"
        try:
            await save_upload(reference_video, temp_path, size_limit_mb=50)
            storage = get_storage_provider()
            reference_key = validate_object_key(
                f"quarantine/{user['id']}/cartoon-references/{project_id}{suffix}",
                expected_prefix=f"quarantine/{user['id']}",
            )
            metadata = await storage.upload(temp_path, reference_key, content_type="application/octet-stream")
            reference_generation = metadata.generation
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "The reference video could not be uploaded. Try again.") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    async def enqueue(db):
        period = await reserve_cartoon_period(db, str(user["id"]), duration_seconds, metered=metered)
        new_job = await create_job(user["id"], "cartoon_generate", payload={"cartoon_project_id": project_id}, db=db)
        await db.execute(
            """INSERT INTO cartoon_projects(
                 id,user_id,title,prompt,duration_seconds,aspect_ratio,style,language,text_model,tts_model,
                 status,progress,stage,storyboard_json,assets_json,reference_key,reference_generation,
                 created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,'queued',0,'queued',?,'{}',?,?,?,?)""",
            (
                project_id, user["id"], title, prompt, duration_seconds, aspect_ratio, style, language,
                PROJECT_STORY_MODELS[story_planner], tts_model, json.dumps(storyboard, ensure_ascii=False),
                reference_key, reference_generation, timestamp, timestamp,
            ),
        )
        await db.execute("UPDATE cartoon_projects SET assets_json=?,job_id=? WHERE id=?",
                         (json.dumps({"_preferred_voice": voice_id}), new_job, project_id))
        if metered:
            await db.execute("UPDATE cartoon_projects SET usage_period_key=? WHERE id=?", (period, project_id))
        return new_job

    try:
        job_id = await run_in_transaction(enqueue, operation_name="queue cartoon and reserve duration")
    except Exception as exc:
        if reference_key:
            try:
                await get_storage_provider().delete(reference_key, generation=reference_generation)
            except Exception:
                pass
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(503, "Cartoon Studio could not queue this project. Please retry.") from exc
    try:
        await dispatch_job(background_tasks, _run_media_job, job_id)
    except Exception as exc:
        await update_job(job_id, 0, "failed", "Cartoon rendering service is not configured. Please contact support.", "failed", "CARTOON_JOB_LAUNCH_FAILED")
        await execute(
            "UPDATE cartoon_projects SET status='failed',stage='failed',error=?,updated_at=? WHERE id=?",
            ("Cartoon rendering service is not configured. Please contact support.", _now(), project_id),
        )
        if reference_key:
            try:
                await get_storage_provider().delete(reference_key, generation=reference_generation)
            except Exception:
                pass
        raise HTTPException(503, "Cartoon rendering service is temporarily unavailable.") from exc
    row = await _owned_project(project_id, user["id"])
    return _project_out(row)


@router.get("/projects")
async def list_cartoon_projects(user: dict = Depends(current_user)) -> list[dict[str, Any]]:
    rows = await fetch_all(
        """SELECT p.*,j.status AS job_status,j.progress AS job_progress,
                  j.stage AS job_stage,j.message AS job_message
           FROM cartoon_projects p LEFT JOIN jobs j ON j.id=p.job_id
           WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT 20""",
        (user["id"],),
    )
    return [_project_out(row) for row in rows]


@router.get("/projects/{project_id}")
async def get_cartoon_project(project_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    row = await _owned_project(project_id, user["id"])
    job = await event_payload(str(row.get("job_id") or "")) if row.get("job_id") else None
    return _project_out(row, job, include_timeline=True)


@router.post("/projects/{project_id}/retry")
async def retry_cartoon_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(current_user),
) -> dict[str, Any]:
    row = await _owned_project(project_id, user["id"])
    if row.get("status") != "failed":
        raise HTTPException(409, "Only a failed cartoon can be retried.")
    if not _project_out(row)["storyboard"].get("scenes"):
        if row.get("text_model") == NVIDIA_STORY_MODEL:
            await _nvidia_key_for_request(user, "")
        elif not await _provider_key(user["id"]):
            raise HTTPException(409, "Reconnect your OpenRouter API key before retrying.")
    metered = await usage_schema_ready()

    async def enqueue(db):
        period = await reserve_cartoon_period(db, str(user["id"]), int(row["duration_seconds"]), metered=metered)
        current = await (await db.execute(
            "SELECT status FROM cartoon_projects WHERE id=? AND user_id=?", (project_id, user["id"]),
        )).fetchone()
        if not current or current[0] != "failed":
            raise HTTPException(409, "Only a failed cartoon can be retried.")
        new_job = await create_job(user["id"], "cartoon_generate", payload={"cartoon_project_id": project_id}, db=db)
        await db.execute(
            """UPDATE cartoon_projects SET job_id=?,status='queued',progress=0,stage='queued',error=NULL,updated_at=?
               WHERE id=? AND user_id=?""",
            (new_job, _now(), project_id, user["id"]),
        )
        if metered:
            await db.execute("UPDATE cartoon_projects SET usage_period_key=? WHERE id=?", (period, project_id))
        return new_job

    try:
        job_id = await run_in_transaction(enqueue, operation_name="retry cartoon and reserve duration")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Cartoon Studio could not queue this retry. Please try again.") from exc
    try:
        await dispatch_job(background_tasks, _run_media_job, job_id)
    except Exception as exc:
        await update_job(job_id, 0, "failed", "Cartoon rendering service is temporarily unavailable.", "failed", "CARTOON_JOB_LAUNCH_FAILED")
        await execute(
            "UPDATE cartoon_projects SET status='failed',stage='failed',error=?,updated_at=? WHERE id=?",
            ("Cartoon rendering service is temporarily unavailable.", _now(), project_id),
        )
        raise HTTPException(503, "Cartoon rendering service is temporarily unavailable.") from exc
    updated = await _owned_project(project_id, user["id"])
    return _project_out(updated)


@router.get("/projects/{project_id}/download")
async def cartoon_download_url(project_id: str, user: dict = Depends(current_user)) -> dict[str, Any]:
    row = await _owned_project(project_id, user["id"])
    if row.get("status") != "ready" or not row.get("output_key"):
        raise HTTPException(409, "This cartoon is not ready to download yet.")
    key = validate_object_key(
        str(row["output_key"]),
        expected_prefix=f"users/{user['id']}/cartoons/{project_id}",
    )
    if object_storage_provider_name() in {"gcs", "s3"}:
        url = await get_storage_provider().signed_download_url(
            key, filename=f"clipkaro-cartoon-{project_id}.mp4", ttl_seconds=600,
        )
        return {"url": url, "expires_in": 600}
    settings = get_settings()
    return {"url": f"{settings.api_prefix}/cartoon-studio/projects/{project_id}/file", "expires_in": 0}


@router.get("/projects/{project_id}/file")
async def download_cartoon_file(project_id: str, user: dict = Depends(current_user)) -> FileResponse:
    row = await _owned_project(project_id, user["id"])
    if row.get("status") != "ready" or not row.get("output_key"):
        raise HTTPException(409, "This cartoon is not ready to download yet.")
    key = validate_object_key(
        str(row["output_key"]),
        expected_prefix=f"users/{user['id']}/cartoons/{project_id}",
    )
    root = get_settings().storage_root.resolve()
    path = (root / key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "The cartoon file is no longer available.")
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(row.get("title") or "cartoon"))[:50].strip("-") or "cartoon"
    return FileResponse(path, media_type="video/mp4", filename=f"{safe_title}.mp4")

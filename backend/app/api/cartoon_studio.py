from __future__ import annotations

import json
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.database import distributed_advisory_lock, execute, fetch_all, fetch_one
from app.services.distributed_rate_limit import consume_rate_limit
from app.services.auth import current_user
from app.services.cartoon_speech import SYSTEM_URDU_TTS_MODEL, system_urdu_tts_model_row
from app.services.cartoon_story import resolve_cartoon_language
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


OPENROUTER_ROOT = "https://openrouter.ai/api/v1"
TEXT_MODEL = "z-ai/glm-5.3-flash"
PREFERRED_TTS = [
    "hexgrad/kokoro-82m",
    "google/gemini-3.1-flash-tts-preview",
    "x-ai/grok-voice-tts-1.0",
    "mistralai/voxtral-mini-tts-2603",
    "microsoft/mai-voice-2",
    "deepgram/aura-2",
    "minimax/speech-2.8-turbo",
    SYSTEM_URDU_TTS_MODEL,
]
ALLOWED_DURATIONS = {15, 30, 45, 60}
ALLOWED_RATIOS = {"9:16", "16:9", "1:1", "4:5"}
ALLOWED_STYLES = {"2d-cartoon", "storybook", "anime-inspired", "flat-vector", "cinematic-jannat"}
ALLOWED_LANGUAGES = {"auto", "en", "hi", "hinglish", "mr", "ur"}


class ProviderKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=20, max_length=500)


async def cartoon_studio_user(user: dict = Depends(current_user)) -> dict:
    if not bool(user.get("cartoon_studio_access_override")):
        raise HTTPException(403, "Cartoon Studio beta access is not enabled for this account.")
    return user


@router.get("/capabilities")
async def cartoon_capabilities(user: dict = Depends(cartoon_studio_user)) -> dict:
    return {"engine_version": "story-v3", "storyboard_version": 3, "aspect_ratios": ["9:16", "16:9", "1:1", "4:5"]}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _provider_key(user_id: str) -> str | None:
    row = await fetch_one(
        "SELECT api_key_ciphertext FROM cartoon_provider_credentials WHERE user_id=? AND provider='openrouter'",
        (user_id,),
    )
    if not row:
        return None
    try:
        return decrypt_provider_key(str(row["api_key_ciphertext"]))
    except CartoonCredentialError as exc:
        raise HTTPException(409, "Reconnect your OpenRouter API key securely before continuing.") from exc


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


def _models_with_preset_voices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    models = [
        item for item in rows
        if isinstance(item.get("supported_voices"), list)
        and any(str(voice).strip() for voice in item["supported_voices"])
    ]
    models.append(system_urdu_tts_model_row())
    return models


def _project_out(row: dict[str, Any], job: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        storyboard = json.loads(str(row.get("storyboard_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        storyboard = {}

    try:
        editable_available = bool(json.loads(str(row.get("assets_json") or "{}")).get("_editable"))
    except (ValueError, TypeError, AttributeError):
        editable_available = False
    job = job or {}
    job_status = str(job.get("status") or row.get("job_status") or "")
    project_status = str(row.get("status") or "queued")
    status = "ready" if project_status == "ready" else (job_status or project_status)
    progress = job.get("progress", row.get("job_progress", row.get("progress", 0)))
    stage = job.get("stage") or row.get("job_stage") or row.get("stage") or "queued"
    message = job.get("message") or row.get("job_message")
    error = row.get("error") or (message if status == "failed" else None)

    return {
        "id": row["id"],
        "job_id": row.get("job_id"),
        "title": row.get("title") or "Cartoon story",
        "prompt": row.get("prompt") or "",
        "duration_seconds": int(row.get("duration_seconds") or 30),
        "aspect_ratio": row.get("aspect_ratio") or "9:16",
        "style": row.get("style") or "2d-cartoon",
        "language": row.get("language") or "auto",
        "status": status,
        "progress": max(0, min(100, int(progress or 0))),
        "stage": stage,
        "error": error,
        "storyboard": storyboard if isinstance(storyboard, dict) else {},
        "editable_available": editable_available,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def _owned_project(project_id: str, user_id: str) -> dict[str, Any]:
    row = await fetch_one("SELECT * FROM cartoon_projects WHERE id=? AND user_id=?", (project_id, user_id))
    if not row:
        raise HTTPException(404, "Cartoon project not found.")
    return row


@router.get("/providers")
async def get_providers(user: dict = Depends(cartoon_studio_user)) -> dict[str, Any]:
    row = await fetch_one(
        "SELECT api_key_masked,validated_at FROM cartoon_provider_credentials WHERE user_id=? AND provider='openrouter'",
        (user["id"],),
    )
    return {
        "openrouter": {
            "connected": bool(row),
            "masked_key": row.get("api_key_masked") if row else "",
            "validated_at": row.get("validated_at") if row else None,
        }
    }


@router.post("/providers/openrouter")
async def save_openrouter_key(body: ProviderKeyRequest, user: dict = Depends(cartoon_studio_user)) -> dict[str, Any]:
    key = body.api_key.strip()
    if not key.startswith("sk-or-"):
        raise HTTPException(422, "This does not look like an OpenRouter API key.")
    # Validate the key without making a billable generation request.
    await _models(key, "text")
    try:
        encrypted_key = encrypt_provider_key(key)
    except CartoonCredentialError as exc:
        raise HTTPException(503, "Secure provider-key storage is not configured. Please contact support.") from exc
    timestamp = _now()
    await execute(
        """INSERT INTO cartoon_provider_credentials(
             user_id,provider,api_key_ciphertext,api_key_masked,api_key_fingerprint,
             validated_at,created_at,updated_at
           ) VALUES (?,'openrouter',?,?,?,?,?,?)
           ON CONFLICT(user_id,provider) DO UPDATE SET
             api_key_ciphertext=excluded.api_key_ciphertext,
             api_key_masked=excluded.api_key_masked,
             api_key_fingerprint=excluded.api_key_fingerprint,
             validated_at=excluded.validated_at,updated_at=excluded.updated_at""",
        (
            user["id"], encrypted_key, mask_provider_key(key),
            fingerprint_provider_key(key), timestamp, timestamp, timestamp,
        ),
    )
    return {"connected": True, "masked_key": mask_provider_key(key), "validated_at": timestamp}


@router.delete("/providers/openrouter", status_code=204)
async def delete_openrouter_key(user: dict = Depends(cartoon_studio_user)) -> None:
    await execute(
        "DELETE FROM cartoon_provider_credentials WHERE user_id=? AND provider='openrouter'",
        (user["id"],),
    )


@router.get("/tts-models")
async def list_tts_models(user: dict = Depends(cartoon_studio_user)) -> dict[str, Any]:
    key = await _provider_key(user["id"])
    if not key:
        raise HTTPException(409, "Connect your OpenRouter API key first.")
    rows = _models_with_preset_voices(await _models(key, "speech"))
    by_id = {str(item.get("id")): item for item in rows if item.get("id")}
    ordered = [by_id.pop(model_id) for model_id in PREFERRED_TTS if model_id in by_id]
    ordered.extend(sorted(by_id.values(), key=lambda item: str(item.get("name") or ""))[:12])
    models = []
    for item in ordered[:15]:
        models.append({
            "id": item.get("id"),
            "name": item.get("name") or item.get("id"),
            "voices": item.get("supported_voices") or [],
            "description": str(item.get("description") or "")[:220],
        })
    if not models:
        raise HTTPException(503, "No speech models are currently available for this OpenRouter account.")
    return {"models": models, "default_model": models[0]["id"]}


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
    reference_video: UploadFile | None = File(default=None),
    user: dict = Depends(cartoon_studio_user),
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
    language = resolve_cartoon_language(language, prompt)
    api_key = await _provider_key(user["id"])
    if not api_key:
        raise HTTPException(409, "Add your OpenRouter API key before creating a cartoon.")
    if not await consume_rate_limit(
        str(user["id"]), group="cartoon_studio_create", limit=5, window_seconds=3600,
    ):
        raise HTTPException(429, "You have reached the Cartoon Studio creation limit. Try again later.")
    active = await fetch_one(
        "SELECT id FROM cartoon_projects WHERE user_id=? AND status IN ('queued','processing') LIMIT 1",
        (user["id"],),
    )
    if active:
        raise HTTPException(409, "You already have a cartoon rendering. Wait for it to finish before starting another.")
    speech_models = _models_with_preset_voices(await _models(api_key, "speech"))
    speech_ids = {str(item.get("id")) for item in speech_models}
    if not tts_model:
        tts_model = next((item for item in PREFERRED_TTS if item in speech_ids), "")
        if not tts_model and speech_models:
            tts_model = str(speech_models[0].get("id") or "")
    if not tts_model or tts_model not in speech_ids:
        raise HTTPException(422, "Select a currently available text-to-speech model.")
    if tts_model == SYSTEM_URDU_TTS_MODEL and language != "ur":
        raise HTTPException(422, "Select Urdu as the story language to use the word-timed system Urdu voice.")

    if style == "cinematic-jannat" and (
        language != "ur" or tts_model != SYSTEM_URDU_TTS_MODEL
    ):
        raise HTTPException(
            422,
            "The Jannat story preset uses Urdu and the System Urdu word-timed voice.",
        )

    selected_model = next(item for item in speech_models if item["id"] == tts_model)
    if voice_id and voice_id not in selected_model.get("supported_voices", []):
        raise HTTPException(422, "Choose a voice supported by the selected speech model.")
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

    async with distributed_advisory_lock(f"cartoon-studio-create:{user['id']}"):
        active = await fetch_one(
            "SELECT id FROM cartoon_projects WHERE user_id=? AND status IN ('queued','processing') LIMIT 1",
            (user["id"],),
        )
        if active:
            if reference_key:
                try:
                    await get_storage_provider().delete(reference_key, generation=reference_generation)
                except Exception:
                    pass
            raise HTTPException(409, "You already have a cartoon rendering. Wait for it to finish before starting another.")

        await execute(
            """INSERT INTO cartoon_projects(
                 id,user_id,title,prompt,duration_seconds,aspect_ratio,style,language,text_model,tts_model,
                 status,progress,stage,storyboard_json,assets_json,reference_key,reference_generation,
                 created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,'queued',0,'queued','{}','{}',?,?,?,?)""",
            (
                project_id, user["id"], title, prompt, duration_seconds, aspect_ratio, style, language,
                TEXT_MODEL, tts_model, reference_key, reference_generation, timestamp, timestamp,
            ),
        )
        try:
            await execute("UPDATE cartoon_projects SET assets_json=? WHERE id=?", (json.dumps({"_preferred_voice": voice_id}), project_id))
            job_id = await create_job(
                user["id"], "cartoon_generate", payload={"cartoon_project_id": project_id},
            )
            await execute(
                "UPDATE cartoon_projects SET job_id=?,updated_at=? WHERE id=?",
                (job_id, timestamp, project_id),
            )
        except Exception as exc:
            await execute(
                "DELETE FROM cartoon_projects WHERE id=? AND user_id=?",
                (project_id, user["id"]),
            )
            if reference_key:
                try:
                    await get_storage_provider().delete(reference_key, generation=reference_generation)
                except Exception:
                    pass
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
async def list_cartoon_projects(user: dict = Depends(cartoon_studio_user)) -> list[dict[str, Any]]:
    rows = await fetch_all(
        """SELECT p.*,j.status AS job_status,j.progress AS job_progress,
                  j.stage AS job_stage,j.message AS job_message
           FROM cartoon_projects p LEFT JOIN jobs j ON j.id=p.job_id
           WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT 20""",
        (user["id"],),
    )
    return [_project_out(row) for row in rows]


@router.get("/projects/{project_id}")
async def get_cartoon_project(project_id: str, user: dict = Depends(cartoon_studio_user)) -> dict[str, Any]:
    row = await _owned_project(project_id, user["id"])
    job = await event_payload(str(row.get("job_id") or "")) if row.get("job_id") else None
    return _project_out(row, job)


@router.post("/projects/{project_id}/retry")
async def retry_cartoon_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(cartoon_studio_user),
) -> dict[str, Any]:
    row = await _owned_project(project_id, user["id"])
    if row.get("status") != "failed":
        raise HTTPException(409, "Only a failed cartoon can be retried.")
    if not await _provider_key(user["id"]):
        raise HTTPException(409, "Reconnect your OpenRouter API key before retrying.")
    if not await consume_rate_limit(
        str(user["id"]), group="cartoon_studio_create", limit=5, window_seconds=3600,
    ):
        raise HTTPException(429, "You have reached the Cartoon Studio retry limit. Try again later.")
    async with distributed_advisory_lock(f"cartoon-studio-create:{user['id']}"):
        active = await fetch_one(
            "SELECT id FROM cartoon_projects WHERE user_id=? AND status IN ('queued','processing') LIMIT 1",
            (user["id"],),
        )
        if active:
            raise HTTPException(409, "Another cartoon is already rendering. Wait for it to finish before retrying.")
        try:
            job_id = await create_job(user["id"], "cartoon_generate", payload={"cartoon_project_id": project_id})
            await execute(
                """UPDATE cartoon_projects SET job_id=?,status='queued',progress=0,stage='queued',error=NULL,updated_at=?
                   WHERE id=? AND user_id=?""",
                (job_id, _now(), project_id, user["id"]),
            )
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


@router.get("/projects/{project_id}/editable")
async def cartoon_editable_url(project_id: str, user: dict = Depends(cartoon_studio_user)) -> dict:
    row = await _owned_project(project_id, user["id"])
    try:
        saved = json.loads(row.get("assets_json") or "{}").get("_editable", {})
    except (ValueError, TypeError, AttributeError):
        saved = {}
    if row.get("status") != "ready" or not saved.get("key"):
        raise HTTPException(409, "This project has no V3 editable package.")
    key = validate_object_key(saved["key"], expected_prefix=f"users/{user['id']}/cartoons/{project_id}")
    if object_storage_provider_name() in {"gcs", "s3"}:
        url = await get_storage_provider().signed_download_url(key, filename=f"clipkaro-editable-{project_id}.zip", ttl_seconds=600)
        return {"url": url, "expires_in": 600}
    return {"url": f"{get_settings().api_prefix}/cartoon-studio/projects/{project_id}/editable-file", "expires_in": 0}


@router.get("/projects/{project_id}/editable-file")
async def cartoon_editable_file(project_id: str, user: dict = Depends(cartoon_studio_user)):
    if object_storage_provider_name() in {"gcs", "s3"}:
        raise HTTPException(404, "Use the editable download URL.")
    row = await _owned_project(project_id, user["id"])
    try:
        saved = json.loads(row.get("assets_json") or "{}").get("_editable", {})
    except (ValueError, TypeError, AttributeError):
        saved = {}
    if row.get("status") != "ready" or not saved.get("key"):
        raise HTTPException(409, "Editable assets are unavailable.")
    key = validate_object_key(saved["key"], expected_prefix=f"users/{user['id']}/cartoons/{project_id}")
    root = get_settings().storage_root.resolve()
    path = (root / key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Editable assets are unavailable.")
    return FileResponse(path, media_type="application/zip", filename=f"clipkaro-editable-{project_id}.zip")


@router.get("/projects/{project_id}/download")
async def cartoon_download_url(project_id: str, user: dict = Depends(cartoon_studio_user)) -> dict[str, Any]:
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
async def download_cartoon_file(project_id: str, user: dict = Depends(cartoon_studio_user)) -> FileResponse:
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

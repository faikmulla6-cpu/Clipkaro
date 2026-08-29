import asyncio
import secrets
import logging
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse
from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one, run_in_transaction
from app.schemas.api import (
    AnalyseRequest, BrandKitRequest, ClipOut, ClipPatch, ExportOut, ExportRequest,
    ProjectPatch, ScheduleRequest, UsageOut, UserOut,
)
from app.services.auth import current_user, require_role
from app.services.jobs import create_job, event_payload, update_job, utcnow
from app.services.rendering import create_edited_srt, create_srt, timed_words
from app.services.render_gate import render_short_limited
from app.services.caption_layout import build_caption_cards
from app.services.caption_styles import public_caption_styles
from app.services.india_quality import (
    caption_segments_for_export, effective_caption_position, language_profile,
    transcript_review_summary,
)
from app.services.transcript_review import effective_segments_for_video
from app.services.transcription import transcribe
from app.services.source_caption_detection import detect_burned_captions
from app.services.storage import get_storage_provider, validate_object_key
from app.services.roman_hindi import add_roman_display_text
from app.services.pipeline_provenance import PIPELINE_VERSION, stamp_segments, transcript_state
from app.services.semantic_ranker import find_best_clips
from app.core.version import APP_VERSION
from app.services.video import probe_metadata, save_upload
from app.services.media_delivery import remove_preview_files
from app.services.storage_paths import confined_export_path, confined_upload_path
from app.services.public_errors import safe_export_failure, safe_project_failure
from app.services.billing import PLAN_CATALOG, sync_subscription_if_needed, usage_period_key

router = APIRouter()
logger = logging.getLogger("clipkaro.pipeline")
PLAN_LIMITS = {key: int(value["exports"]) for key, value in PLAN_CATALOG.items()}
PLAN_PROCESSING_MINUTES = {key: float(value["processing_minutes"]) for key, value in PLAN_CATALOG.items()}
PLAN_MAX_SOURCE_MINUTES = {
    "free": 15, "mini_pass": 25, "creator": 60, "growth": 180, "pro": 240, "agency": 240,
}
TEMPLATES = [
    {"id":"india-pop","name":"India Pop","category":"Trending","caption_style":"hindi-pop","primary":"#FF6B35","accent":"#FFD84D","best_for":"Hindi & Hinglish"},
    {"id":"clean-educator","name":"Clean Educator","category":"Education","caption_style":"clean","primary":"#DFFF57","accent":"#165F43","best_for":"Classes & explainers"},
    {"id":"podcast-punch","name":"Podcast Punch","category":"Podcast","caption_style":"bold","primary":"#B5A7FF","accent":"#211A3A","best_for":"Interviews"},
    {"id":"business-edge","name":"Business Edge","category":"Business","caption_style":"kinetic","primary":"#65D7FF","accent":"#102C3A","best_for":"Founders & coaches"},
    {"id":"minimal-story","name":"Minimal Story","category":"Story","caption_style":"minimal","primary":"#FFFFFF","accent":"#222222","best_for":"Personal stories"},
    {"id":"spiritual-calm","name":"Spiritual Calm","category":"Spiritual","caption_style":"clean","primary":"#E6C873","accent":"#173B32","best_for":"Faith & reflection"},
]


def now() -> datetime: return datetime.now(timezone.utc)


def _export_is_expired(row: dict) -> bool:
    """Enforce export retention at read time, not only during hourly cleanup."""
    value = str(row.get("expires_at") or "").strip()
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc) <= now()
    except ValueError:
        # Existing rows should always contain ISO timestamps. A malformed expiry
        # is treated as unavailable rather than extending private media forever.
        return True


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _age_seconds(value: object) -> int | None:
    parsed = _parse_timestamp(value)
    if not parsed:
        return None
    return max(0, int((now() - parsed).total_seconds()))


async def audit(user_id: str | None, event: str, entity_type: str = "", entity_id: str = "", metadata: dict | None = None) -> None:
    await execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), user_id, event, entity_type, entity_id, json.dumps(metadata or {}), utcnow()))


def as_user(row: dict) -> UserOut:
    return UserOut(**{**row, "onboarding_complete": bool(row.get("onboarding_complete", 0))})


@router.get("/health")
async def health() -> dict:
    from app.services.video import ffmpeg_available
    media_ready = ffmpeg_available()
    return {"status":"healthy" if media_ready else "degraded","service":"clipkaro-api",
            "version":APP_VERSION,"ffmpeg":media_ready,"realtime":"sse"}


@router.get("/caption-styles")
async def caption_styles() -> list[dict]:
    """Canonical style metadata used by Creator Studio's live preview."""
    return public_caption_styles()


@router.get("/system/preflight")
async def system_preflight(user: dict = Depends(current_user)) -> dict:
    # Authenticated only. The service returns sanitized status codes/messages and
    # never provider response bodies, hostnames, API keys, SMTP credentials or secrets.
    from app.services.production_preflight import production_preflight
    return await production_preflight()


@router.get("/plans")
async def plans() -> list[dict]:
    return [
        {
            "id": key,
            "name": value["name"],
            "price": value["price"],
            "exports": value["exports"],
            "processing_minutes": value["processing_minutes"],
            "watermark": value["watermark"],
            "resolution": value["resolution"],
            "billing": value["billing"],
            "popular": bool(value.get("popular")),
        }
        for key, value in PLAN_CATALOG.items()
    ]


@router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)) -> UserOut: return as_user(user)


@router.patch("/auth/me", response_model=UserOut)
async def update_me(body: dict, user: dict = Depends(current_user)) -> UserOut:
    name = str(body.get("name", user["name"])).strip()[:60]
    if len(name) < 2: raise HTTPException(422, "Name is too short.")
    await execute("UPDATE users SET name=?,onboarding_complete=1,updated_at=? WHERE id=?", (name, utcnow(), user["id"]))
    updated = await fetch_one("SELECT id,name,email,plan,role,onboarding_complete,created_at FROM users WHERE id=?", (user["id"],))
    return as_user(updated)


async def get_usage_for(user: dict) -> UsageOut:
    user = await sync_subscription_if_needed(user)
    plan = str(user.get("plan") or "free")
    export_limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    minute_limit = PLAN_PROCESSING_MINUTES.get(plan, PLAN_PROCESSING_MINUTES["free"])
    period = usage_period_key(user)
    row = await fetch_one("SELECT * FROM usage WHERE user_id=? AND month=?", (user["id"], period))
    if not row:
        await execute(
            "INSERT INTO usage(id,user_id,month,source_minutes,exports_used,exports_limit) VALUES (?, ?, ?, 0, 0, ?)",
            (str(uuid.uuid4()), user["id"], period, export_limit),
        )
        used, minutes = 0, 0.0
    else:
        used, minutes = int(row["exports_used"]), float(row["source_minutes"])
        if int(row["exports_limit"]) != export_limit:
            await execute("UPDATE usage SET exports_limit=? WHERE id=?", (export_limit, row["id"]))
    return UsageOut(
        plan=plan, exports_used=used, exports_limit=export_limit,
        exports_remaining=max(export_limit-used, 0), source_minutes=round(minutes, 1),
        processing_minutes_limit=minute_limit,
        processing_minutes_remaining=round(max(minute_limit-minutes, 0), 1),
        period_key=period,
    )


@router.get("/usage", response_model=UsageOut)
async def usage(user: dict = Depends(current_user)) -> UsageOut: return await get_usage_for(user)


async def _persist_suggestions(video: dict, segments: list[dict], language: str) -> list[dict]:
    timestamp = utcnow()
    origin="asr" if any(item.get("asr_provider") for item in segments) else "manual"
    segments=stamp_segments(segments,origin)
    # Ranking can involve remote semantic scoring. Complete it before mutating
    # the accepted transcript/current moments so a transient ranking failure can
    # never leave a new transcript paired with stale suggestions.
    clips = await find_best_clips(segments, language, 8)
    rows = [(
        c["id"], video["id"], c["start_time"], c["end_time"], c["hook"], c["title"], c["reason"], c["text"],
        c["score"], json.dumps(c["score_breakdown"]), c["platform"], "suggested", timestamp, timestamp
    ) for c in clips]

    async def _persist(db) -> None:
        await db.execute("DELETE FROM transcripts WHERE video_id=?", (video["id"],))
        await db.execute("INSERT INTO transcripts VALUES (?, ?, ?, ?, ?, ?)", (
            str(uuid.uuid4()), video["id"], language,
            " ".join(s.get("display_text") or s["text"] for s in segments), json.dumps(segments), timestamp,
        ))
        await db.execute("UPDATE content_packs SET status='stale',updated_at=? WHERE project_id=? AND status='ready'", (timestamp, video["project_id"]))
        await _retire_previous_clips(db, video["id"], timestamp)
        if rows:
            await db.executemany("INSERT INTO clips VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    await run_in_transaction(_persist, mode="IMMEDIATE", operation_name="persist transcript and ranked moments")
    return clips


async def _persist_suggestions_from_existing_transcript(video: dict, segments: list[dict], language: str) -> list[dict]:
    """Create clip suggestions without mutating or retranscribing a saved transcript."""
    timestamp = utcnow()
    clips = await find_best_clips(segments, language, 8)
    rows = [(
        c["id"], video["id"], c["start_time"], c["end_time"], c["hook"], c["title"], c["reason"], c["text"],
        c["score"], json.dumps(c["score_breakdown"]), c["platform"], "suggested", timestamp, timestamp
    ) for c in clips]

    async def _persist(db) -> None:
        await _retire_previous_clips(db, video["id"], timestamp)
        if rows:
            await db.executemany("INSERT INTO clips VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    await run_in_transaction(_persist, mode="IMMEDIATE", operation_name="replace ranked moments")
    return clips


async def _retire_previous_clips(db, video_id: str, timestamp: str) -> None:
    """Replace current suggestions without destroying historical exports.

    Ready/failed export rows and calendar drafts belong to the user's durable
    history. Deleting an exported clip would cascade through ``exports`` and
    ``scheduled_posts``. Keep any clip that has ever been exported as a hidden
    superseded record; unexported suggestions can be safely removed.
    """
    await db.execute(
        """UPDATE clips SET status='superseded',updated_at=?
           WHERE video_id=? AND status<>'superseded'
             AND EXISTS (SELECT 1 FROM exports e WHERE e.clip_id=clips.id)""",
        (timestamp, video_id),
    )
    await db.execute(
        """DELETE FROM clips WHERE video_id=? AND status<>'superseded'
             AND NOT EXISTS (SELECT 1 FROM exports e WHERE e.clip_id=clips.id)""",
        (video_id,),
    )


async def _process_project(
    job_id: str,
    project_id: str,
    video_id: str,
    user: dict,
    asr_route: str = "legacy",
    force_transcribe: bool = False,
    source_override: Path | None = None,
) -> None:
    video = await fetch_one("SELECT * FROM videos WHERE id=?", (video_id,))
    try:
        source_path = source_override or confined_upload_path((video or {}).get("file_path"))
        if source_path is None or not source_path.is_file():
            raise ValueError("The source video is unavailable in ClipKaro private storage.")
        # Durable worker retries can occur after an API request succeeded but
        # before job completion was recorded. Reuse a current accepted transcript
        # instead of spending provider quota a second time. Explicit user
        # re-analysis sets ``force_transcribe`` and must never take this recovery
        # shortcut, otherwise changing the language would silently reuse old ASR.
        existing = await fetch_one(
            "SELECT language,segments_json FROM transcripts WHERE video_id=? ORDER BY created_at DESC LIMIT 1",
            (video_id,),
        )
        if existing:
            existing_segments = json.loads(existing["segments_json"])
            # A forced re-analysis must bypass a transcript produced by an older
            # job, but a retry of the *same* durable job may safely reuse the
            # transcript it already committed. This avoids a second paid ASR call
            # after a worker restart between persistence and final job status.
            same_job_transcript = bool(
                existing_segments
                and str(existing_segments[0].get("processing_job_id") or "") == str(job_id)
            )
            if force_transcribe and not same_job_transcript:
                existing = None
        if existing:
            existing_segments = json.loads(existing["segments_json"])
            state = transcript_state(existing_segments, get_settings().effective_require_asr_consensus, get_settings().effective_require_forced_alignment)
            ranked = await fetch_one("SELECT COUNT(*) count FROM clips WHERE video_id=? AND status<>'superseded'", (video_id,))
            clip_count = int((ranked or {}).get("count") or 0)
            if state["current"] and state["export_safe"] and clip_count == 0:
                clips = await _persist_suggestions_from_existing_transcript(video, existing_segments, existing.get("language") or "auto")
                if clips:
                    await execute("UPDATE projects SET status='ready',progress=100,stage='ready',error=NULL,updated_at=? WHERE id=?", (utcnow(), project_id))
                    await execute("UPDATE videos SET status='ready' WHERE id=?", (video_id,))
                    await update_job(job_id, 100, "ready", f"Recovered {len(clips)} moments from existing verified transcript", "completed")
                    return
            if state["current"] and state["export_safe"] and clip_count > 0:
                await execute("UPDATE projects SET status='ready',progress=100,stage='ready',error=NULL,updated_at=? WHERE id=?", (utcnow(), project_id))
                await execute("UPDATE videos SET status='ready' WHERE id=?", (video_id,))
                await update_job(job_id, 100, "ready", "Reused existing verified transcript", "completed")
                return
        await update_job(job_id, 8, "validating", "Reading video and checking quality")
        await execute("UPDATE projects SET status='processing',progress=8,stage='validating',updated_at=? WHERE id=?", (utcnow(), project_id))
        metadata = await probe_metadata(source_path)
        source_caption_scan = await detect_burned_captions(source_path, float(metadata["duration"]))
        limits = await get_usage_for(user)
        active_plan = limits.plan
        max_minutes = PLAN_MAX_SOURCE_MINUTES.get(active_plan, PLAN_MAX_SOURCE_MINUTES["free"])
        source_minutes = float(metadata["duration"]) / 60
        if source_minutes > max_minutes:
            raise ValueError(f"Your {PLAN_CATALOG[active_plan]['name']} plan supports a single source video up to {max_minutes} minutes.")
        # A successful project's source minutes were already finalized when it
        # was first processed. Explicit language correction must not charge the
        # same uploaded source twice. If the earlier attempt never finalized,
        # the reservation trigger below still performs the authoritative quota
        # check when the video returns to ``validated``.
        if not force_transcribe and source_minutes > limits.processing_minutes_remaining + 1e-6:
            raise ValueError(
                f"You have {limits.processing_minutes_remaining:g} Karo Minutes left in this billing period, "
                f"but this video needs {source_minutes:.1f}. Upgrade or wait for your quota to refresh."
            )
        await execute("UPDATE videos SET duration=?,width=?,height=?,status='validated' WHERE id=?",
                      (metadata["duration"],metadata["width"],metadata["height"],video_id))
        await update_job(job_id, 22, "audio", "Extracting and cleaning audio")
        await execute("UPDATE projects SET progress=22,stage='audio',updated_at=? WHERE id=?", (utcnow(), project_id))
        await update_job(job_id, 38, "transcribing", "Creating a timestamped transcript")
        await execute("UPDATE projects SET progress=38,stage='transcribing',updated_at=? WHERE id=?", (utcnow(), project_id))
        project_settings=await fetch_one("SELECT language FROM projects WHERE id=?",(project_id,))
        language_hint=(project_settings or {}).get("language","auto")
        # Legacy source contract was: await transcribe(Path(video["file_path"])
        # Cloud jobs supply an equivalent bounded scratch path without changing routing.
        language, segments = await transcribe(source_path, get_settings().whisper_model, language_hint, request_id=job_id, asr_route=asr_route)
        for segment in segments:
            segment["processing_job_id"] = job_id
        duration=float(metadata["duration"]); clean_segments=[]
        for segment in segments:
            segment_start=max(0.0,float(segment.get("start",0)))
            segment_end=min(duration,float(segment.get("end",0)))
            text=str(segment.get("text","")).strip()
            if segment_end<=segment_start or not text or segment_start>=duration: continue
            clean={**segment,"start":segment_start,"end":segment_end,"text":text,
                   "source_has_burned_captions":source_caption_scan["detected"],
                   "source_caption_confidence":source_caption_scan["confidence"],
                   "source_caption_band":source_caption_scan.get("band_start")}
            if segment.get("words"):
                clean["words"]=[word for word in segment["words"]
                                if segment_start<=float(word.get("start",-1))<segment_end
                                and float(word.get("end",-1))>segment_start and str(word.get("text","")).strip()]
            clean_segments.append(clean)
        segments=clean_segments
        await update_job(job_id, 70, "ranking", "Scoring hooks, clarity, emotion, value and flow")
        await execute("UPDATE projects SET progress=70,stage='ranking',updated_at=? WHERE id=?", (utcnow(), project_id))
        clips = await _persist_suggestions(video, segments, language)
        if not clips: raise ValueError("We found speech, but no complete 20–90 second moments. Try a longer source video.")
        await update_job(job_id, 92, "finishing", f"Preparing {len(clips)} clip previews")
        # Karo Minutes are reserved at the validated transition and finalized by
        # the database when the video reaches ready. Never increment them here;
        # doing so would double-charge the same source in local/legacy execution.
        await execute("UPDATE videos SET status='ready' WHERE id=?", (video_id,))
        await execute("UPDATE projects SET status='ready',progress=100,stage='ready',error=NULL,updated_at=? WHERE id=?", (utcnow(),project_id))
        await update_job(job_id,100,"ready",f"{len(clips)} high-potential moments are ready","completed")
        ranking_source = "groq" if any(clip.get("ranking_source") == "groq" for clip in clips) else "local"
        await audit(user["id"],"project.processed","project",project_id,{"clips":len(clips),"language":language,"ranking_source":ranking_source})
    except Exception as exc:
        message = safe_project_failure(exc)
        logger.exception("Project processing failed project_id=%s stage=%s", project_id,
                         (await fetch_one("SELECT stage FROM projects WHERE id=?", (project_id,)) or {}).get("stage"))
        current = await fetch_one("SELECT progress FROM projects WHERE id=?", (project_id,))
        failed_progress = int((current or {}).get("progress", 0))
        await execute("UPDATE projects SET status='failed',stage='failed',error=?,updated_at=? WHERE id=?", (message,utcnow(),project_id))
        await update_job(job_id,failed_progress,"failed",message,"failed",message)



@router.get("/projects")
async def list_projects(user: dict = Depends(current_user)) -> list[dict]:
    return await fetch_all("""SELECT p.*,v.id video_id,v.duration,v.width,v.height,v.status video_status,
      (SELECT COUNT(*) FROM clips c WHERE c.video_id=v.id AND c.status<>'superseded') clip_count,
      (SELECT COUNT(*) FROM exports e JOIN clips c2 ON c2.id=e.clip_id WHERE c2.video_id=v.id AND e.status='ready') export_count
      FROM projects p LEFT JOIN videos v ON v.project_id=p.id WHERE p.user_id=? ORDER BY p.updated_at DESC""",(user["id"],))



@router.patch("/projects/{project_id}")
async def patch_project(project_id:str,body:ProjectPatch,user:dict=Depends(current_user))->dict:
    project=await fetch_one("SELECT * FROM projects WHERE id=? AND user_id=?",(project_id,user["id"]))
    if not project: raise HTTPException(404,"Project not found.")
    values=body.model_dump(exclude_none=True)
    if values:
        columns=",".join(f"{key}=?" for key in values)
        await execute(f"UPDATE projects SET {columns},updated_at=? WHERE id=?",tuple(values.values())+(utcnow(),project_id))
    return await fetch_one("SELECT * FROM projects WHERE id=?",(project_id,))


@router.delete("/projects/{project_id}",status_code=204)
async def delete_project(project_id:str,user:dict=Depends(current_user)) -> Response:
    video=await fetch_one("SELECT v.* FROM videos v JOIN projects p ON p.id=v.project_id WHERE p.id=? AND p.user_id=?",(project_id,user["id"]))
    if not video: raise HTTPException(404,"Project not found.")
    if get_settings().normalized_storage_backend == "gcs":
        storage = get_storage_provider()
        source_key = validate_object_key(str(video.get("file_path") or ""), expected_prefix=f"users/{user['id']}/projects/{project_id}")
        await storage.delete(source_key, generation=video.get("object_generation"))
        exports=await fetch_all("SELECT e.id,e.output_path,e.object_generation FROM exports e JOIN clips c ON c.id=e.clip_id WHERE c.video_id=?",(video["id"],))
        for item in exports:
            key = validate_object_key(str(item.get("output_path") or ""), expected_prefix=f"users/{user['id']}/exports/{item['id']}")
            await storage.delete(key, generation=item.get("object_generation"))
        await execute("DELETE FROM projects WHERE id=?",(project_id,)); await audit(user["id"],"project.deleted","project",project_id)
        return Response(status_code=204)
    source_path = confined_upload_path(video.get("file_path"))
    if source_path is not None:
        source_path.unlink(missing_ok=True)
    else:
        logger.warning("Refused out-of-storage project source deletion video_id=%s", video.get("id"))
    remove_preview_files(str(video["id"]))
    exports=await fetch_all("SELECT e.output_path FROM exports e JOIN clips c ON c.id=e.clip_id WHERE c.video_id=?",(video["id"],))
    for item in exports:
        export_path = confined_export_path(item.get("output_path"))
        if export_path is not None:
            export_path.unlink(missing_ok=True)
        else:
            logger.warning("Refused out-of-storage export deletion project_id=%s", project_id)
    await execute("DELETE FROM projects WHERE id=?",(project_id,)); await audit(user["id"],"project.deleted","project",project_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/analyse",response_model=list[ClipOut])
async def analyse_project(project_id:str,body:AnalyseRequest,user:dict=Depends(current_user))->list[ClipOut]:
    video=await fetch_one("SELECT v.* FROM videos v JOIN projects p ON p.id=v.project_id WHERE p.id=? AND p.user_id=?",(project_id,user["id"]))
    if not video: raise HTTPException(404,"Project not found.")
    if body.segments:
        language,segments=body.language,[x.model_dump() for x in body.segments]
        segments=add_roman_display_text(segments,language in {"hi","ur","hinglish"})
    else:
        source_path = confined_upload_path(video.get("file_path"))
        if source_path is None or not source_path.is_file():
            raise HTTPException(410,"The source video has expired from private media storage.")
        language,segments=await transcribe(source_path,get_settings().whisper_model,body.language)
    clips=await _persist_suggestions(video,segments,language)
    await execute("UPDATE projects SET status='ready',progress=100,stage='ready',updated_at=? WHERE id=?",(utcnow(),project_id))
    return [ClipOut(**{**c,"transcript_text":c["text"]}) for c in clips]


@router.get("/jobs/{job_id}")
async def job_status(job_id:str,user:dict=Depends(current_user))->dict:
    row=await fetch_one("SELECT * FROM jobs WHERE id=? AND user_id=?",(job_id,user["id"]))
    if not row: raise HTTPException(404,"Job not found.")
    return row


@router.get("/jobs/{job_id}/events")
async def job_events(job_id:str,request:Request,user:dict=Depends(current_user))->EventSourceResponse:
    owned=await fetch_one("SELECT id FROM jobs WHERE id=? AND user_id=?",(job_id,user["id"]))
    if not owned: raise HTTPException(404,"Job not found.")
    async def stream():
        last=None
        while True:
            if await request.is_disconnected(): break
            payload=await event_payload(job_id)
            if not payload: break
            serialized=json.dumps(payload)
            if serialized!=last: yield {"event":"progress","data":serialized}; last=serialized
            if payload["status"] in {"completed","failed"}: yield {"event":"done","data":serialized}; break
            await asyncio.sleep(.65)
    return EventSourceResponse(stream(),headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@router.patch("/clips/{clip_id}",response_model=ClipOut)
async def patch_clip(clip_id:str,body:ClipPatch,user:dict=Depends(current_user))->ClipOut:
    clip=await fetch_one("""SELECT c.* FROM clips c JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
      WHERE c.id=? AND p.user_id=?""",(clip_id,user["id"]))
    if not clip: raise HTTPException(404,"Clip not found.")
    if clip.get("status") == "superseded": raise HTTPException(409,"This moment belongs to an earlier analysis. Open the current project moments instead.")
    values=body.model_dump(exclude_none=True)
    start,end=values.get("start_time",clip["start_time"]),values.get("end_time",clip["end_time"])
    if end<=start or end-start>180: raise HTTPException(422,"Clip must be between 1 and 180 seconds.")
    if values:
        columns=",".join(f"{key}=?" for key in values)
        await execute(f"UPDATE clips SET {columns},updated_at=? WHERE id=?",tuple(values.values())+(utcnow(),clip_id))
        if "transcript_text" in values:
            await execute(
                """UPDATE content_packs SET status='stale',updated_at=?
                   WHERE project_id=(SELECT p.id FROM projects p JOIN videos v ON v.project_id=p.id WHERE v.id=?)
                     AND status='ready'""",
                (utcnow(), clip["video_id"]),
            )
    row=await fetch_one("SELECT * FROM clips WHERE id=?",(clip_id,)); row["score_breakdown"]=json.loads(row.pop("score_breakdown_json"))
    return ClipOut(**row)


@router.get("/clips/{clip_id}/captions")
async def clip_captions(clip_id:str,user:dict=Depends(current_user))->dict:
    clip=await fetch_one("""SELECT c.* FROM clips c JOIN videos v ON v.id=c.video_id
      JOIN projects p ON p.id=v.project_id WHERE c.id=? AND p.user_id=?""",(clip_id,user["id"]))
    if not clip: raise HTTPException(404,"Clip not found.")
    if clip.get("status") == "superseded": raise HTTPException(409,"This moment belongs to an earlier analysis and cannot be edited against the new transcript.")
    transcript, segments = await effective_segments_for_video(clip["video_id"])
    words=timed_words(segments,clip["start_time"],clip["end_time"], allow_synthetic=True)
    relative_words=[{**word,"start":round(float(word["start"])-clip["start_time"],3),
                     "end":round(float(word["end"])-clip["start_time"],3)} for word in words]
    cards=build_caption_cards(relative_words)
    language=(transcript or {}).get("language","unknown")
    profile=language_profile(segments, language)
    review=transcript_review_summary(segments, language)
    return {"language":language,"clip_start":clip["start_time"],
            "clip_end":clip["end_time"],"words":relative_words,
            "india_quality":profile,
            "review_suggested":review["review_suggested"],
            "review_reasons":review["review_reasons"],
            "review_segment_count":review["review_segment_count"],
            "source_has_burned_captions":any(bool(item.get("source_has_burned_captions")) for item in segments),
            "source_caption_band":next((item.get("source_caption_band") for item in segments
                                        if item.get("source_caption_band") is not None),None),
            "cards":[{"start":card.start,"end":card.end,"lines":card.lines,
                      "words":[{"start":w["start"],"end":w["end"],"text":w["text"],
                                "confidence":w.get("confidence",1)} for w in card.words]} for card in cards]}


async def _render_export(job_id:str,export_id:str,clip:dict,video:dict,request:ExportRequest,output:Path,brand:dict|None,source_override:Path|None=None)->None:
    srt=output.with_suffix(".srt")
    try:
        await update_job(job_id,12,"preparing","Preparing crop, captions and brand style")
        await execute("UPDATE exports SET status='processing',progress=12 WHERE id=?",(export_id,))
        transcript, segments = await effective_segments_for_video(video["id"])
        raw_segments = json.loads(transcript["segments_json"]) if transcript else []
        settings=get_settings()
        state=transcript_state(segments,settings.effective_require_asr_consensus,settings.effective_require_forced_alignment)
        if not state["export_safe"]:
            raise RuntimeError(f"Export blocked by transcript safety gate: {state['reason']}.")
        source_text=" ".join(str(item.get("display_text") or item.get("text", "")).strip() for item in segments
                             if float(item.get("end", 0)) > clip["start_time"] and float(item.get("start", 0)) < clip["end_time"])
        normalize=lambda value: re.sub(r"\s+", " ", value or "").strip().casefold()
        caption_segments=caption_segments_for_export(
            segments,(transcript or {}).get("language","auto"),
            india_quality_mode=request.india_quality_mode,
            caption_language_style=request.caption_language_style,
        )
        correction_in_clip = any(
            segment.get("corrected_text")
            and float(segment.get("end", 0)) > clip["start_time"]
            and float(segment.get("start", 0)) < clip["end_time"]
            for segment in segments
        )
        if correction_in_clip:
            reference=timed_words(raw_segments,clip["start_time"],clip["end_time"])
            create_edited_srt(source_text,clip["end_time"]-clip["start_time"],srt,
                              reference,clip["start_time"])
        elif transcript and normalize(clip.get("transcript_text")) == normalize(source_text):
            create_srt(caption_segments,clip["start_time"],clip["end_time"],srt)
        elif clip.get("transcript_text"):
            reference=timed_words(segments,clip["start_time"],clip["end_time"])
            create_edited_srt(clip["transcript_text"],clip["end_time"]-clip["start_time"],srt,
                              reference,clip["start_time"])
        await update_job(job_id,35,"rendering","Rendering your social-ready video")
        await execute("UPDATE exports SET progress=35 WHERE id=?",(export_id,))
        source_path = source_override or confined_upload_path(video.get("file_path"))
        if source_path is None or not source_path.is_file():
            raise RuntimeError("The source video is unavailable in ClipKaro private storage.")
        scan=await detect_burned_captions(source_path,float(video.get("duration") or clip["end_time"]))
        # Existing burned-in subtitles are advisory context only. Lower, Above
        # and Centre are creator-authoritative and render exactly as selected.
        preserve_band = scan.get("band_start") if scan["detected"] else None
        if request.preserve_source_captions and preserve_band is None:
            preserve_band = 0.82
        caption_position=effective_caption_position(
            request.india_quality_mode, request.preserve_source_captions, request.caption_position
        )
        await render_short_limited(
            source_path, output, clip["start_time"], clip["end_time"],
            srt if srt.exists() else None, request.hook_text or clip["hook"], request.watermark,
            request.resolution, request.aspect_ratio, request.caption_style,
            (brand or {}).get("logo_text") or "", (brand or {}).get("primary_color") or "#DFFF57",
            request.focus_x, caption_position, [item.model_dump() for item in request.crop_keyframes],
            preserve_band,
        )
        await update_job(job_id,92,"optimizing","Optimizing MP4 for fast social upload")
        await execute("UPDATE exports SET status='ready',progress=100 WHERE id=?",(export_id,))
        await execute("UPDATE clips SET status='exported',updated_at=? WHERE id=?",(utcnow(),clip["id"]))
        # Export quota was reserved atomically when the exports row was created;
        # the ready transition finalizes that reservation. Never increment it a
        # second time here.
        await update_job(job_id,100,"ready","Your Short is ready to download","completed")
        await audit(clip["user_id"],"export.completed","export",export_id)
    except Exception as exc:
        message = safe_export_failure(exc)
        logger.exception("Export rendering failed export_id=%s clip_id=%s", export_id, clip.get("id"))
        await execute("UPDATE exports SET status='failed',error=? WHERE id=?",(message,export_id))
        await update_job(job_id,0,"failed","Export failed","failed",message)
    finally: srt.unlink(missing_ok=True)



@router.get("/exports")
async def list_exports(user:dict=Depends(current_user))->list[dict]:
    rows = await fetch_all("""SELECT e.*,c.title,c.hook,p.title project_title,
      j.id job_id,j.status job_status,j.stage job_stage,j.message job_message,j.updated_at job_updated_at
      FROM exports e JOIN clips c ON c.id=e.clip_id
      JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
      LEFT JOIN jobs j ON j.id=(
        SELECT id FROM jobs WHERE export_id=e.id AND kind='render_export' ORDER BY updated_at DESC LIMIT 1
      )
      WHERE e.user_id=? ORDER BY e.created_at DESC""",(user["id"],))
    # The hourly cleanup loop is best-effort. Never advertise an expired private
    # file as ready merely because its physical deletion has not run yet.
    for row in rows:
        if row.get("status") == "ready" and _export_is_expired(row):
            row["status"] = "expired"
        row["job_age_seconds"] = _age_seconds(row.get("job_updated_at") or row.get("created_at"))
        row["attention_needed"] = row.get("status") in {"queued", "processing"} and (row.get("job_age_seconds") or 0) > 600
    return rows


@router.get("/exports/{export_id}",response_model=ExportOut)
async def export_status(export_id:str,user:dict=Depends(current_user))->ExportOut:
    row=await fetch_one("SELECT * FROM exports WHERE id=? AND user_id=?",(export_id,user["id"]))
    if not row: raise HTTPException(404,"Export not found.")
    expired = _export_is_expired(row)
    status = "expired" if expired and row["status"] == "ready" else row["status"]
    return ExportOut(id=row["id"],status=status,progress=row["progress"],download_url=f"/api/v1/exports/{export_id}/download" if status=="ready" else None,expires_at=row["expires_at"])


@router.get("/exports/{export_id}/download")
async def download_export(export_id:str,user:dict=Depends(current_user)):
    row=await fetch_one("SELECT * FROM exports WHERE id=? AND user_id=?",(export_id,user["id"]))
    settings = get_settings()
    if row and row["status"] == "ready" and not _export_is_expired(row) and settings.normalized_storage_backend == "gcs":
        key = validate_object_key(str(row.get("output_path") or ""), expected_prefix=f"users/{user['id']}/exports/{export_id}")
        url = await get_storage_provider().signed_download_url(
            key, filename="clipkaro-short.mp4", ttl_seconds=min(300, max(60, settings.gcs_download_url_ttl_seconds)),
        )
        return RedirectResponse(url, status_code=307, headers={"Cache-Control": "private, no-store"})
    output_path = confined_export_path((row or {}).get("output_path"))
    if not row or row["status"]!="ready" or _export_is_expired(row) or output_path is None or not output_path.is_file():
        raise HTTPException(404,"Export is not ready or has expired.")
    return FileResponse(
        output_path, media_type="video/mp4", filename="clipkaro-short.mp4",
        headers={"Cache-Control": "private, no-store"},
    )



@router.get("/templates")
async def templates(_:dict=Depends(current_user))->list[dict]: return TEMPLATES


@router.get("/brand-kits")
async def brand_kits(user:dict=Depends(current_user))->list[dict]: return await fetch_all("SELECT * FROM brand_kits WHERE user_id=? ORDER BY is_default DESC,updated_at DESC",(user["id"],))


@router.post("/brand-kits",status_code=201)
async def create_brand_kit(body:BrandKitRequest,user:dict=Depends(current_user))->dict:
    limits = await get_usage_for(user)
    if limits.plan not in {"creator","growth","pro","agency"}: raise HTTPException(403,"Brand kits start on the Creator plan.")
    kit_id=str(uuid.uuid4()); timestamp=utcnow()
    if body.is_default: await execute("UPDATE brand_kits SET is_default=0 WHERE user_id=?",(user["id"],))
    await execute("INSERT INTO brand_kits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (kit_id,user["id"],body.name,body.primary_color,body.accent_color,body.font_family,body.logo_text,body.caption_preset,int(body.is_default),timestamp,timestamp))
    return await fetch_one("SELECT * FROM brand_kits WHERE id=?",(kit_id,))


@router.delete("/brand-kits/{kit_id}",status_code=204)
async def delete_brand_kit(kit_id:str,user:dict=Depends(current_user))->Response:
    await execute("DELETE FROM brand_kits WHERE id=? AND user_id=?",(kit_id,user["id"])); return Response(status_code=204)


@router.get("/calendar")
async def calendar(user:dict=Depends(current_user))->list[dict]: return await fetch_all("SELECT * FROM scheduled_posts WHERE user_id=? ORDER BY scheduled_for",(user["id"],))


@router.post("/calendar",status_code=201)
async def schedule(body:ScheduleRequest,user:dict=Depends(current_user))->dict:
    export=await fetch_one("SELECT id FROM exports WHERE id=? AND user_id=? AND status='ready'",(body.export_id,user["id"]))
    if not export: raise HTTPException(422,"Choose a completed export before scheduling.")
    scheduled_for = body.scheduled_for if body.scheduled_for.tzinfo else body.scheduled_for.replace(tzinfo=timezone.utc)
    if scheduled_for <= now():
        raise HTTPException(422,"Choose a future date and time for this calendar draft.")
    item_id=str(uuid.uuid4())
    await execute("INSERT INTO scheduled_posts VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
                  (item_id,user["id"],body.export_id,body.platform,body.caption,body.hashtags,scheduled_for.isoformat(),utcnow()))
    return await fetch_one("SELECT * FROM scheduled_posts WHERE id=?",(item_id,))


@router.delete("/calendar/{post_id}",status_code=204)
async def delete_scheduled_post(post_id:str,user:dict=Depends(current_user))->Response:
    row=await fetch_one("SELECT id FROM scheduled_posts WHERE id=? AND user_id=?",(post_id,user["id"]))
    if not row: raise HTTPException(404,"Calendar item not found.")
    await execute("DELETE FROM scheduled_posts WHERE id=? AND user_id=?",(post_id,user["id"]))
    await audit(user["id"],"calendar.item_deleted","scheduled_post",post_id)
    return Response(status_code=204)


@router.get("/analytics")
async def analytics(user:dict=Depends(current_user))->dict:
    summary=await fetch_one("""SELECT
      (SELECT COUNT(*) FROM projects p WHERE p.user_id=?) projects,
      (SELECT COUNT(*) FROM clips c JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
         WHERE p.user_id=? AND c.status<>'superseded') clips,
      (SELECT COALESCE(AVG(c.score),0) FROM clips c JOIN videos v ON v.id=c.video_id JOIN projects p ON p.id=v.project_id
         WHERE p.user_id=? AND c.status<>'superseded') avg_score,
      (SELECT COUNT(*) FROM exports e WHERE e.user_id=? AND e.status='ready') exports,
      (SELECT COALESCE(SUM(v.duration),0) FROM videos v JOIN projects p ON p.id=v.project_id WHERE p.user_id=?) seconds_processed""",
      (user["id"],user["id"],user["id"],user["id"],user["id"]))
    categories=await fetch_all("SELECT category,COUNT(*) count FROM projects WHERE user_id=? GROUP BY category ORDER BY count DESC",(user["id"],))
    activity=await fetch_all("""SELECT substr(CAST(created_at AS TEXT),1,10) AS "day",COUNT(*) AS exports FROM exports WHERE user_id=? AND status='ready'
      GROUP BY 1 ORDER BY 1 DESC LIMIT 14""",(user["id"],))
    usage=await get_usage_for(user)
    seconds = summary.pop("seconds_processed")
    return {"summary":{**summary,"avg_score":round(summary["avg_score"],1),"minutes_processed":round(seconds/60,1)},
            "usage":usage.model_dump(),"categories":categories,"activity":list(reversed(activity))}


@router.get("/admin/overview")
async def admin_overview(_:dict=Depends(require_role("admin")))->dict:
    from app.services.jobs import worker_runtime_snapshot
    users=await fetch_one("SELECT COUNT(*) n FROM users"); projects=await fetch_one("SELECT COUNT(*) n FROM projects")
    jobs=await fetch_all("SELECT status,COUNT(*) count FROM jobs GROUP BY status")
    jobs_by_kind=await fetch_all("SELECT kind,status,COUNT(*) count FROM jobs GROUP BY kind,status ORDER BY kind,status")
    recent_jobs=await fetch_all("""SELECT j.id,j.kind,j.status,j.progress,j.stage,j.message,j.error,j.project_id,j.export_id,
      j.created_at,j.updated_at,p.title project_title,c.title clip_title,u.email user_email
      FROM jobs j
      LEFT JOIN projects p ON p.id=j.project_id
      LEFT JOIN exports e ON e.id=j.export_id
      LEFT JOIN clips c ON c.id=e.clip_id
      LEFT JOIN users u ON u.id=j.user_id
      WHERE j.kind IN ('process_video','upgrade_pipeline','render_export')
      ORDER BY j.updated_at DESC LIMIT 40""")
    stale_seconds=max(60,int(get_settings().job_claim_stale_seconds))
    for row in recent_jobs:
        row["age_seconds"]=_age_seconds(row.get("updated_at"))
        row["stale"] = row.get("status") in {"queued","processing"} and (row.get("age_seconds") or 0) > stale_seconds
    exports=await fetch_one("SELECT COUNT(*) n FROM exports WHERE status='ready'")
    return {
      "users":users["n"],"projects":projects["n"],"exports":exports["n"],
      "jobs":jobs,"jobs_by_kind":jobs_by_kind,"recent_jobs":recent_jobs,
      "worker":await worker_runtime_snapshot(),"stale_after_seconds":stale_seconds,
    }

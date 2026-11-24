"""V3 orchestration; provider calls live only here, never in deterministic render fixtures."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from .cartoon_story import StoryValidationError, normalize_director_story, RATIOS
from .cartoon_speech import CAPTIONS_ONLY_MODEL, SYSTEM_KOKORO_TTS_MODEL
from .cartoon_story_render import build_story_project, caption_guide_assets, schedule_speech
from .cartoon_story_score import build_story_stems
from .cartoon_timing import SPEECH_LINE_CAPTION_SOURCE
from .speech_activity import detect_speech_regions

logger = logging.getLogger("clipkaro.cartoon")


async def audio_alignment(path: Path, language: str) -> list[dict]:
    """Use the installed ASR pipeline only when the chosen TTS lacks word timestamps."""
    from .transcription import transcribe
    from .roman_hindi import romanize_hindi
    try:
        _, segments = await transcribe(
            path, language_hint="hi" if language == "hinglish" else language,
            generated_dialogue=True,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        logger.warning("Cartoon word alignment failed: reason=%s", type(exc).__name__)
        raise StoryValidationError(
            "ClipKaro could not align the generated speech for captions. The voice is saved for retry."
        ) from exc
    output=[]
    for segment in segments:
        for word in segment.get("words",[]):
            text=str(word.get("word") or word.get("text") or "").strip()
            if language=="hinglish":text=romanize_hindi(text)
            start,end=float(word.get("start",0)),float(word.get("end",0))
            if text and end>start:
                output.append({"text":text,"offset":round(start*10_000_000),"duration":round((end-start)*10_000_000)})
    if not output:
        raise StoryValidationError("The speech provider has no word timestamps and audio alignment returned no words. Choose a word-timed voice.")
    return output


async def speech_caption_window(path: Path, duration: float) -> tuple[float, float] | None:
    try:
        regions = await asyncio.to_thread(detect_speech_regions, path)
    except (RuntimeError, OSError) as exc:
        logger.warning("Cartoon caption speech detection failed: reason=%s", type(exc).__name__)
        return None
    if not regions:
        return None
    start = max(0.0, regions[0]["start"])
    end = min(duration, regions[-1]["end"])
    return (start, end) if end - start >= .08 else None


async def run_director_job(job: dict, project: dict, storyboard: dict, project_dir: Path, storage, api_key: str, tts_model: str) -> None:
    # Lazy import reuses the existing worker's storage, subprocess and provider policies.
    from . import cartoon_job as worker
    from app.core.database import execute
    from .jobs import update_job, utcnow
    from .cartoon_audio import build_lip_envelope
    from .video import probe_metadata
    story=normalize_director_story(storyboard,duration=int(project["duration_seconds"]))
    for character in story["characters"]:
        original=next(c for c in storyboard["characters"] if c["id"]==character["id"])
        character["voice_id"]=original.get("voice_id","")
    saved=worker._loads(project.get("assets_json"),{})
    preferred_voice=str(saved.get("_preferred_voice") or "")
    if preferred_voice and story["characters"][0]["voice_id"] == preferred_voice:
        story["narrator_voice_id"]=preferred_voice
    audio_dir=project_dir/"assets"/"audio";audio_dir.mkdir(parents=True,exist_ok=True)
    captions_only = tts_model == CAPTIONS_ONLY_MODEL
    audio = caption_guide_assets(story) if captions_only else []
    lines = [] if captions_only else [line for scene in story["scenes"] for line in scene["speech"]]
    for i,line in enumerate(lines):
        character=next((c for c in story["characters"] if c["id"]==line["speaker_id"]),story["characters"][0])
        voice=story.get("narrator_voice_id",character["voice_id"]) if line["track"]=="narration" else character["voice_id"]
        # Content/voice hash prevents stale speech from being reused after a storyboard edit.
        signature=hashlib.sha256(json.dumps([line["text"],voice,tts_model],ensure_ascii=True).encode()).hexdigest()
        key=f"users/{job['user_id']}/cartoons/{project['id']}/audio/{line['id']}-{signature[:12]}.mp3"
        record=saved.get(line["id"],{})
        path=audio_dir/(line["id"]+".mp3")
        meta=await storage.stat(key) if record.get("signature")==signature else None
        await update_job(job["id"],20+int(35*i/max(1,len(lines))),"voice_generation","Creating timed narration and character dialogue")
        if meta and meta.size>0:
            await storage.download(key,path,generation=record.get("generation"))
            boundaries=record.get("word_boundaries") or []
        else:
            boundaries=await worker._tts_audio(api_key,tts_model,voice,line["text"],path)
        duration=await worker._probe_audio_duration(path)
        if not meta:
            uploaded=await storage.upload(path,key,content_type="audio/mpeg")
            record={"key":key,"generation":uploaded.generation,"signature":signature,"duration":duration,"word_boundaries":boundaries}
            saved[line["id"]]=record
            # Save billable speech before alignment; a failed alignment retry must not buy it again.
            await execute("UPDATE cartoon_projects SET assets_json=?,updated_at=? WHERE id=?",(json.dumps(saved,ensure_ascii=False),utcnow(),project["id"]))
        timing_source=record.get("timing_source","tts_word_boundary") if meta else "tts_word_boundary"
        caption_window = None
        if not boundaries:
            if tts_model == SYSTEM_KOKORO_TTS_MODEL:
                caption_window = await speech_caption_window(path, duration)
                if caption_window is None:
                    raise StoryValidationError("The built-in voice produced no detectable speech. Select captions only to add your own voice.")
                timing_source = SPEECH_LINE_CAPTION_SOURCE
            else:
                try:
                    boundaries=await audio_alignment(path,str(project.get("language") or "auto"))
                    timing_source="audio_asr_alignment"
                except StoryValidationError:
                    caption_window = await speech_caption_window(path, duration)
                    if caption_window is None:
                        raise
                    timing_source = SPEECH_LINE_CAPTION_SOURCE
        envelope=await build_lip_envelope(path)
        record.update(word_boundaries=boundaries,timing_source=timing_source)
        saved[line["id"]]=record
        await execute("UPDATE cartoon_projects SET assets_json=?,updated_at=? WHERE id=?",(json.dumps(saved,ensure_ascii=False),utcnow(),project["id"]))
        audio.append({"id":line["id"],"filename":path.name,"duration":duration,"word_boundaries":boundaries,
                      "lip_envelope":envelope,"timing_source":timing_source,"caption_window":caption_window})
    scheduled,tracks,words=schedule_speech(story,audio)
    stems=await asyncio.to_thread(build_story_stems,audio_dir,scheduled,tracks)
    engine,cli,gsap=worker._engine_paths();node=shutil.which("node") or shutil.which("nodejs")
    bundle=engine/"dist"/"animation.js"
    if not node or not cli.is_file() or not bundle.is_file():
        raise worker.CartoonJobError("Deploy the V3 animation bundle on the media worker.",category="CARTOON_RENDERER_UNAVAILABLE")
    shutil.copy2(bundle,project_dir/"assets"/"animation.js");shutil.copy2(gsap,project_dir/"assets"/"gsap.min.js")
    files=build_story_project({**project,"audio_tracks":stems,"captions_only":captions_only},story,audio)
    for name,content in files.items():(project_dir/name).write_text(content,encoding="utf-8")
    env=os.environ.copy()
    headless=Path("/etc/hyperframes-headless-shell-path")
    if headless.is_file():env["PRODUCER_HEADLESS_SHELL_PATH"]=headless.read_text().strip()
    await update_job(job["id"],68,"checking","Validating the directed animation and audio timeline")
    code,_=await worker._run_cli([node,str(cli),"check","--json"],cwd=project_dir,env=env,timeout=300)
    if code:raise worker.CartoonJobError("V3 composition validation failed. Saved voices are available for retry.",category="CARTOON_RENDER_CHECK_FAILED")
    await update_job(job["id"],76,"rendering","Rendering the story actions and camera shots")
    output=project_dir/"final.mp4"
    code,_=await worker._run_cli([node,str(cli),"render","--quality","high","--workers","1","--low-memory-mode","-o",str(output)],cwd=project_dir,env=env,timeout=1200)
    if code or not output.is_file():raise worker.CartoonJobError("The directed story could not be rendered.",category="CARTOON_RENDER_FAILED")
    metadata=await probe_metadata(output)
    expected_w,expected_h,_=RATIOS[project["aspect_ratio"]]
    if abs(float(metadata["duration"])-project["duration_seconds"])>.15 or int(metadata["width"])!=expected_w or int(metadata["height"])!=expected_h:
        raise worker.CartoonJobError("Rendered dimensions or duration differ from the selected format.",category="CARTOON_RENDER_DURATION_INVALID")
    await asyncio.to_thread(verify_render_audio,output,bool(lines))
    # Export local editable HTML, native timing and every independent stem, without provider credentials.
    archive=project_dir/"editable-project.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for name in files:z.write(project_dir/name,name)
        for path in (project_dir/"assets").rglob("*"):
            if path.is_file():z.write(path,path.relative_to(project_dir))
        for path in (engine/"animation").glob("*"):
            if path.suffix in {".tsx",".js"}:z.write(path,"animation-source/"+path.name)
        z.write(engine/"ANIMATION-NOTICES.md","ANIMATION-NOTICES.md")
    root=f"users/{job['user_id']}/cartoons/{project['id']}"
    editable=await storage.upload(archive,root+"/editable-project.zip",content_type="application/zip")
    saved["_editable"]={"key":root+"/editable-project.zip","generation":editable.generation}
    saved["_line_timed_captions"] = not captions_only and any(asset["caption_window"] is not None for asset in audio)
    saved["_voiceover_kit"] = True
    stored=await storage.upload(output,root+"/final.mp4",content_type="video/mp4")
    await execute("""UPDATE cartoon_projects SET status='ready',progress=100,stage='ready',output_key=?,
        output_generation=?,error=NULL,storyboard_json=?,assets_json=?,updated_at=? WHERE id=?""",
        (root+"/final.mp4",stored.generation,json.dumps(story,ensure_ascii=False),json.dumps(saved),utcnow(),project["id"]))
    await update_job(job["id"],100,"ready","Your animated story is ready","completed")


def verify_render_audio(path: Path, speech_expected: bool) -> None:
    probe=subprocess.run(["ffprobe","-v","error","-show_streams","-of","json",str(path)],capture_output=True,check=True,timeout=30)
    streams=json.loads(probe.stdout)["streams"]
    if not any(s["codec_type"]=="audio" for s in streams):
        raise StoryValidationError("Final video has no audio track.")
    # Reject unexplained digital silence; quiet suspense is allowed, missing tracks are not.
    result=subprocess.run(["ffmpeg","-hide_banner","-i",str(path),"-vn","-af","silencedetect=noise=-55dB:d=3","-f","null","-"],capture_output=True,check=True,timeout=60)
    if b"silence_start" in result.stderr:
        raise StoryValidationError("Final video contains more than three seconds of unexplained silence.")

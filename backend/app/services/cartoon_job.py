from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.database import execute, fetch_one
from app.services.cartoon_renderer import build_cartoon_project
from app.services.cartoon_speech import SYSTEM_URDU_TTS_MODEL, system_urdu_tts_model_row, synthesize_edge_tts
from app.services.cartoon_audio import build_lip_envelope
from app.services.cartoon_score import build_jannat_audio_stems
from app.services.cartoon_timing import approximate_word_boundaries, build_episode_lip_envelope, normalize_word_boundaries
from app.services.cartoon_story import (
    StoryValidationError,
    director_prompt,
    director_response_schema,
    normalize_director_story,
    prepare_director_reply,
)
from app.services.cartoon_security import decrypt_provider_key
from app.services.jobs import update_job, utcnow
from app.services.storage import validate_object_key
from app.services.video import probe_metadata

logger = logging.getLogger("clipkaro.cartoon")
OPENROUTER_ROOT = "https://openrouter.ai/api/v1"
STORY_MODEL = "z-ai/glm-5.3-flash"
STORY_COMPLETION_TOKENS = 16_384
VOICE_PREFERENCES = {
    "male": [
        "Puck", "Fenrir", "Charon", "Orus", "rex", "leo", "en_paul_neutral",
        "am_adam", "am_fenrir", "am_puck", "am_michael", "bm_daniel", "bm_george",
        "hm_omega", "hm_psi", "pm_alex", "gb_oliver_neutral", "de-DE-Klaus:MAI-Voice-2",
        "aura-2-orion-en", "aura-2-hermes-en", "aura-2-atlas-en",
        "English_magnetic_voiced_man", "English_Trustworth_Man",
    ],
    "female": [
        "Kore", "Aoede", "Leda", "Zephyr", "eve", "ara",
        "af_heart", "af_bella", "af_kore", "bf_alice", "bf_emma", "hf_alpha",
        "hf_beta", "if_sara", "gb_jane_curious", "gb_jane_confident", "fr_marie_neutral",
        "es-MX-Valeria:MAI-Voice-2", "fr-FR-Soleil:MAI-Voice-2",
        "aura-2-thalia-en", "aura-2-asteria-en", "aura-2-athena-en", "aura-2-hera-en",
        "English_radiant_girl", "English_Upbeat_Woman", "English_CalmWoman",
    ],
    "child": [
        "Leda", "Puck", "Kore", "Zephyr", "hf_alpha", "hf_beta", "af_heart",
        "am_puck", "am_santa", "pm_santa", "pf_dora", "ef_dora",
        "English_SadTeen", "English_Strong-WilledBoy",
    ],
    "elder": [
        "Fenrir", "Charon", "Orus", "leo", "sal", "am_michael", "bm_george",
        "hm_omega", "hm_psi", "English_MaturePartner", "English_MatureBoss",
        "English_WiseScholar", "English_Wiselady",
    ],
    "neutral": [
        "Zephyr", "Aoede", "Puck", "Kore", "en_paul_neutral", "gb_oliver_neutral",
        "sal", "af_alloy", "af_river", "English_FriendlyPerson",
        "en-US-Harper:MAI-Voice-2",
    ],
}
ALLOWED_ENVIRONMENTS = {"forest", "city", "beach", "space", "castle", "school", "home", "mountain", "desert", "garden"}
ALLOWED_EXPRESSIONS = {"happy", "sad", "surprised", "angry", "curious", "neutral", "scared"}
ALLOWED_MOTIONS = {"idle", "walk", "run", "jump", "wave", "point", "look"}
ALLOWED_CAMERAS = {"push-in", "pan-left", "pan-right", "zoom-out", "static"}
ALLOWED_SPECIES = {"human", "fox", "cat", "dog", "rabbit", "bear", "owl", "robot"}


class CartoonJobError(RuntimeError):
    def __init__(self, message: str, *, category: str = "CARTOON_GENERATION_FAILED") -> None:
        super().__init__(message)
        self.public_message = message
        self.category = category


def _loads(value: Any, fallback: Any) -> Any:
    try:
        result = json.loads(str(value or ""))
        return result if isinstance(result, type(fallback)) else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _provider_error(response: httpx.Response, *, task: str) -> CartoonJobError:
    if response.status_code in {401, 403}:
        return CartoonJobError(
            "OpenRouter rejected your API key. Reconnect your key in Cartoon Studio and retry.",
            category="CARTOON_PROVIDER_AUTH",
        )
    if response.status_code == 402:
        return CartoonJobError(
            "Your OpenRouter credits are exhausted. Add credits to your OpenRouter account and retry. ClipKaro did not charge you for AI inference.",
            category="CARTOON_PROVIDER_QUOTA",
        )
    if response.status_code == 429:
        return CartoonJobError(
            "OpenRouter rate limit reached. Wait a little and retry; ClipKaro has not charged you for this failed request.",
            category="CARTOON_PROVIDER_RATE_LIMIT",
        )
    if response.status_code >= 500:
        return CartoonJobError(
            f"OpenRouter is temporarily unavailable during {task}. Your project is safe; retry shortly.",
            category="CARTOON_PROVIDER_TEMPORARY",
        )
    return CartoonJobError(
        f"OpenRouter could not complete {task}. Check the selected model and your provider account, then retry.",
        category="CARTOON_PROVIDER_REQUEST",
    )


async def _openrouter_models(api_key: str, modality: str) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0)) as client:
            response = await client.get(
                f"{OPENROUTER_ROOT}/models",
                params={"output_modalities": modality},
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise CartoonJobError("Could not reach OpenRouter. Check your connection and retry.", category="CARTOON_PROVIDER_TEMPORARY") from exc
    if response.status_code >= 400:
        raise _provider_error(response, task="model discovery")
    try:
        payload = response.json()
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        return [row for row in rows if isinstance(row, dict)]
    except (ValueError, json.JSONDecodeError):
        raise CartoonJobError("OpenRouter returned an unreadable model list.", category="CARTOON_PROVIDER_REQUEST")


def _voice_for(character: dict[str, Any], voices: list[str], language: str = "auto") -> str:
    voice_type = str(character.get("voice_type") or "neutral").lower()
    if language == "ur":
        urdu_preferences = {
            "male": ["ur-PK-AsadNeural"],
            "female": ["ur-PK-UzmaNeural"],
            "child": ["ur-PK-UzmaNeural"],
            "elder": ["ur-PK-UzmaNeural"],
            "neutral": ["ur-PK-UzmaNeural"],
        }
        preferences = urdu_preferences.get(voice_type, urdu_preferences["neutral"])
    elif language in {"hi", "hinglish"}:
        hindi_preferences = {
            "male": ["hm_omega", "hm_psi"],
            "female": ["hf_alpha", "hf_beta"],
            "child": ["hf_alpha", "hf_beta", "hm_omega"],
            "elder": ["hm_omega", "hm_psi", "hf_alpha"],
            "neutral": ["hf_alpha", "hm_omega", "hf_beta", "hm_psi"],
        }
        preferences = hindi_preferences.get(voice_type, hindi_preferences["neutral"])
    else:
        preferences = VOICE_PREFERENCES.get(voice_type, VOICE_PREFERENCES["neutral"])
    for preferred in preferences:
        if preferred in voices:
            return preferred
    return voices[0] if voices else "Puck"


def _safe_id(value: Any, fallback: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or ""))[:32].strip("-")
    return result or fallback


def _safe_color(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate) else fallback


def _safe_species(value: Any, role: Any, name: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in ALLOWED_SPECIES:
        return candidate
    identity = f"{role or ''} {name or ''}".lower()
    for species in ("fox", "owl", "rabbit", "cat", "dog", "bear", "robot"):
        if re.search(rf"\b{species}\b", identity):
            return species
    return "human"


def _normalize_storyboard(raw: dict[str, Any], scene_count: int, prompt: str) -> dict[str, Any]:
    characters_raw = raw.get("characters") if isinstance(raw.get("characters"), list) else []
    characters: list[dict[str, Any]] = []
    for index, item in enumerate(characters_raw[:3]):
        if not isinstance(item, dict):
            continue
        appearance = item.get("appearance") if isinstance(item.get("appearance"), dict) else {}
        voice_type = str(item.get("voice_type") or "neutral").lower()
        if voice_type not in {"male", "female", "child", "elder", "neutral"}:
            voice_type = "neutral"
        hair_style = str(appearance.get("hair_style") or "short").lower()
        if hair_style not in {"short", "long", "curly", "spiky", "bald"}:
            hair_style = "short"
        name = str(item.get("name") or f"Character {index+1}")[:40]
        role = str(item.get("role") or "story character")[:100]
        characters.append({
            "id": _safe_id(item.get("id"), f"character-{index+1}"),
            "name": name,
            "role": role,
            "species": _safe_species(item.get("species"), role, name),
            "voice_type": voice_type,
            "appearance": {
                "skin_color": _safe_color(appearance.get("skin_color"), "#E9B58F"),
                "hair_color": _safe_color(appearance.get("hair_color"), "#3D2A25"),
                "shirt_color": _safe_color(appearance.get("shirt_color"), "#E87552"),
                "pants_color": _safe_color(appearance.get("pants_color"), "#405D86"),
                "shoe_color": _safe_color(appearance.get("shoe_color"), "#3A3441"),
                "hair_style": hair_style,
            },
        })
    if not characters:
        characters = [{
            "id": "hero", "name": "Aarav", "role": "curious young explorer", "species": "human", "voice_type": "male",
            "appearance": {"skin_color": "#E9B58F", "hair_color": "#3D2A25", "shirt_color": "#E87552", "pants_color": "#405D86", "shoe_color": "#3A3441", "hair_style": "short"},
        }]
    character_ids = {item["id"] for item in characters}
    scenes_raw = raw.get("scenes") if isinstance(raw.get("scenes"), list) else []
    if not scenes_raw:
        raise CartoonJobError("The story planner returned no scenes. Please try a simpler story.", category="CARTOON_STORY_INVALID")
    scenes: list[dict[str, Any]] = []
    for index in range(scene_count):
        item = scenes_raw[min(index, len(scenes_raw)-1)]
        if not isinstance(item, dict):
            item = {}
        ids = item.get("character_ids") if isinstance(item.get("character_ids"), list) else []
        ids = [_safe_id(value, "") for value in ids]
        ids = [value for value in ids if value in character_ids][:3]
        speaker = _safe_id(item.get("speaker_id"), characters[0]["id"])
        if speaker not in character_ids:
            speaker = characters[0]["id"]
        if speaker not in ids:
            ids.insert(0, speaker)
        environment = str(item.get("environment") or "forest").lower()
        expression = str(item.get("expression") or "happy").lower()
        motion = str(item.get("motion") or "idle").lower()
        camera = str(item.get("camera_move") or "push-in").lower()
        scenes.append({
            "id": f"scene-{index+1}",
            "scene_title": str(item.get("scene_title") or f"Part {index+1}")[:72],
            "environment": environment if environment in ALLOWED_ENVIRONMENTS else "forest",
            "action": str(item.get("action") or "The characters discover something unexpected.")[:120],
            "expression": expression if expression in ALLOWED_EXPRESSIONS else "happy",
            "motion": motion if motion in ALLOWED_MOTIONS else "idle",
            "camera_move": camera if camera in ALLOWED_CAMERAS else "push-in",
            "character_ids": ids,
            "speaker_id": speaker,
            "dialogue": str(item.get("dialogue") or ("Let's see what happens next!" if index == 0 else "We can do this together!"))[:140],
        })
    return {
        "title": str(raw.get("title") or prompt[:64] or "A New Adventure")[:80],
        "summary": str(raw.get("summary") or "")[:300],
        "narration": str(raw.get("narration") or "")[:400],
        "characters": characters,
        "scenes": scenes,
    }


async def _extract_reference_frames(job: dict, project: dict, scratch: Path, storage) -> list[Path]:
    key = str(project.get("reference_key") or "")
    if not key:
        return []
    generation = project.get("reference_generation")
    reference = scratch / "uploads" / f"{project['id']}-reference{Path(key).suffix or '.mp4'}"
    try:
        await storage.download(validate_object_key(key, expected_prefix=f"quarantine/{job['user_id']}"), reference, generation=generation)
        from app.media_job import _scan_source
        await _scan_source(reference, storage, key, generation)
        metadata = await probe_metadata(reference)
        if float(metadata["duration"]) > 90:
            raise CartoonJobError("Reference videos must be 90 seconds or shorter.", category="CARTOON_REFERENCE_TOO_LONG")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise CartoonJobError("FFmpeg is unavailable in the cartoon renderer.", category="CARTOON_RENDERER_UNAVAILABLE")
        duration = float(metadata["duration"])
        times = sorted(set([min(.5, duration*.1), duration*.45, max(.5, duration-.5)]))
        frames: list[Path] = []
        for index, stamp in enumerate(times[:3]):
            frame = scratch / "uploads" / f"cartoon-reference-{index+1}.jpg"
            proc = await asyncio.to_thread(
                subprocess.run,
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(stamp), "-i", str(reference),
                 "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "6", str(frame)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=45,
            )
            if proc.returncode == 0 and frame.is_file() and frame.stat().st_size:
                frames.append(frame)
        if not frames:
            raise CartoonJobError("ClipKaro could not extract readable frames from the reference video.", category="CARTOON_REFERENCE_INVALID")
        await storage.delete(key, generation=generation)
        await execute(
            "UPDATE cartoon_projects SET reference_key=NULL,reference_generation=NULL,updated_at=? WHERE id=?",
            (utcnow(), project["id"]),
        )
        return frames
    except Exception:
        # Quarantined input is never left behind after a failed scan or decode.
        try:
            await storage.delete(key, generation=generation)
        except Exception:
            pass
        raise


async def _generate_storyboard(api_key: str, prompt: str, duration: int, style: str, language: str, frames: list[Path]) -> dict[str, Any]:
    system = "You are ClipKaro's animation director. Return only a validated data storyboard, never code. Plan original characters, timed physical actions, cinematography, narration, dialogue and sound."
    user_text = director_prompt(duration, language, style, prompt)
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for frame in frames:
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
    payload = {
        "model": STORY_MODEL,
        "temperature": 0.65,
        "max_tokens": STORY_COMPLETION_TOKENS,
        # GLM Flash defaults to maximum reasoning, which shares the completion budget.
        "reasoning": {"effort": "low", "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "clipkaro_storyboard", "strict": True, "schema": director_response_schema()},
        },
        "provider": {"require_parameters": True},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
            response = await client.post(
                f"{OPENROUTER_ROOT}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise CartoonJobError("Could not reach OpenRouter while planning your cartoon.", category="CARTOON_PROVIDER_TEMPORARY") from exc
    if response.status_code >= 400:
        raise _provider_error(response, task="story planning")
    try:
        reply = response.json()
        choice = reply["choices"][0]
        if choice.get("finish_reason") == "length":
            usage = reply.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            details = usage.get("completion_tokens_details")
            details = details if isinstance(details, dict) else {}
            completion = usage.get("completion_tokens")
            reasoning = details.get("reasoning_tokens")
            logger.warning(
                "Cartoon planner output truncated: budget=%d completion_tokens=%s reasoning_tokens=%s",
                STORY_COMPLETION_TOKENS,
                completion if type(completion) is int else None,
                reasoning if type(reasoning) is int else None,
            )
            raise CartoonJobError(
                "The story planner ran out of space before finishing its storyboard.",
                category="CARTOON_STORY_TRUNCATED",
            )
        message = choice["message"]["content"]
        if isinstance(message, list):
            message = "".join(str(part.get("text") or "") for part in message if isinstance(part, dict))
        text = str(message or "").strip()
        text = re.sub(r"^\s*\x60{3}(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*\x60{3}\s*$", "", text)
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ValueError("storyboard must be an object")
        return normalize_director_story(prepare_director_reply(raw), duration=duration)
    except StoryValidationError as exc:
        # Validator messages are fixed strings. Never log prompts, outputs or credentials.
        logger.warning("Cartoon storyboard rejected: %s", exc)
        raise CartoonJobError(
            f"The story planner produced an unsupported storyboard. {exc}",
            category="CARTOON_STORY_INVALID",
        ) from exc
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Cartoon planner response could not be read (%s)", type(exc).__name__)
        raise CartoonJobError(
            "The story planner returned an unreadable response.",
            category="CARTOON_STORY_INVALID",
        ) from exc


def _apply_cinematic_jannat_storyboard(storyboard: dict[str, Any]) -> dict[str, Any]:
    """Lock the reference template to one stable Jannat character and bedroom setting."""
    storyboard["characters"] = [{
        "id": "jannat",
        "name": "Jannat",
        "role": "main character",
        "species": "human",
        "voice_type": "female",
        "appearance": {
            "skin_color": "#ca9a85",
            "hair_color": "#121c29",
            "shirt_color": "#306b73",
            "pants_color": "#306b73",
            "shoe_color": "#17202b",
            "hair_style": "long",
        },
    }]
    scenes = storyboard.get("scenes") if isinstance(storyboard.get("scenes"), list) else []
    if len(scenes) != 3:
        raise CartoonJobError(
            "The Jannat cinematic preset requires exactly three 10-second scenes. Regenerate the storyboard and retry.",
            category="CARTOON_CINEMATIC_STORY_INVALID",
        )
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene["environment"] = "home"
        scene["character_ids"] = ["jannat"]
        scene["speaker_id"] = "jannat"
    return storyboard


async def _tts_audio(
    api_key: str, model: str, voice: str, text: str, output: Path,
    *, rate: str = "-8%", volume: str = "-8%", pitch: str = "-3Hz",
) -> list[dict[str, Any]]:
    if model == SYSTEM_URDU_TTS_MODEL:
        try:
            return await synthesize_edge_tts(text, voice, output, rate=rate, volume=volume, pitch=pitch)
        except RuntimeError as exc:
            raise CartoonJobError(str(exc), category="CARTOON_TTS_SYSTEM_FAILED") from exc
    response_format = "pcm" if model.startswith(("google/", "hexgrad/")) else "mp3"
    payload = {"model": model, "input": text, "voice": voice, "response_format": response_format}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            response = await client.post(
                f"{OPENROUTER_ROOT}/audio/speech",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise CartoonJobError("Could not reach the speech provider while generating a character voice.", category="CARTOON_PROVIDER_TEMPORARY") from exc
    if response.status_code >= 400:
        raise _provider_error(response, task="character voice generation")
    if not response.content or len(response.content) < 128:
        raise CartoonJobError("The speech provider returned an empty audio file. Retry or choose another voice model.", category="CARTOON_TTS_EMPTY")

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("audio/"):
        raise CartoonJobError(
            "The speech provider returned an unexpected response instead of audio. Choose another voice model or retry.",
            category="CARTOON_TTS_INVALID_RESPONSE",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")

    if content_type in {"audio/pcm", "audio/l16", "audio/x-pcm"}:
        if not ffmpeg:
            raise CartoonJobError("FFmpeg is unavailable to convert generated speech.", category="CARTOON_RENDERER_UNAVAILABLE")
        header = response.headers.get("content-type", "").lower()
        rate_match = re.search(r"(?:^|;)\s*rate=(\d+)", header)
        channels_match = re.search(r"(?:^|;)\s*channels=(\d+)", header)
        sample_rate = int(rate_match.group(1)) if rate_match else 24000
        channels = int(channels_match.group(1)) if channels_match else 1
        if not 8000 <= sample_rate <= 96000:
            sample_rate = 24000
        if channels not in {1, 2}:
            channels = 1
        raw = output.with_suffix(".pcm")
        raw.write_bytes(response.content)
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le",
                 "-ar", str(sample_rate), "-ac", str(channels), "-i", str(raw),
                 "-codec:a", "libmp3lame", "-q:a", "4", str(output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=90,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CartoonJobError("ClipKaro could not convert the generated character voice.", category="CARTOON_TTS_CONVERSION_FAILED") from exc
        finally:
            raw.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise CartoonJobError("ClipKaro could not convert the generated character voice.", category="CARTOON_TTS_CONVERSION_FAILED")
    elif "wav" in content_type:
        if not ffmpeg:
            raise CartoonJobError("FFmpeg is unavailable to convert generated speech.", category="CARTOON_RENDERER_UNAVAILABLE")
        raw = output.with_suffix(".wav")
        raw.write_bytes(response.content)
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
                 "-codec:a", "libmp3lame", "-q:a", "4", str(output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=90,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CartoonJobError("ClipKaro could not convert the generated character voice.", category="CARTOON_TTS_CONVERSION_FAILED") from exc
        finally:
            raw.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise CartoonJobError("ClipKaro could not convert the generated character voice.", category="CARTOON_TTS_CONVERSION_FAILED")
    elif content_type in {"audio/mpeg", "audio/mp3"}:
        output.write_bytes(response.content)
    else:
        raise CartoonJobError(
            "The speech provider returned an unsupported audio format. Choose another voice model.",
            category="CARTOON_TTS_FORMAT_UNSUPPORTED",
        )

    if not output.is_file() or output.stat().st_size < 128:
        raise CartoonJobError("ClipKaro could not validate the generated character voice file.", category="CARTOON_TTS_CONVERSION_FAILED")
    return []


async def _probe_audio_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise CartoonJobError("FFprobe is required to time generated narration.", category="CARTOON_RENDERER_UNAVAILABLE")
    result = await asyncio.to_thread(
        subprocess.run,
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    if result.returncode != 0:
        raise CartoonJobError("The narration audio could not be timed.", category="CARTOON_TTS_INVALID_RESPONSE")
    try:
        duration = float(result.stdout.decode().strip())
    except ValueError as exc:
        raise CartoonJobError("The narration returned an invalid duration.", category="CARTOON_TTS_INVALID_RESPONSE") from exc
    if not 0.05 <= duration <= 30:
        raise CartoonJobError("The narration duration is outside the supported range.", category="CARTOON_TTS_INVALID_RESPONSE")
    return duration


async def _run_cli(args: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=str(cwd), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise CartoonJobError("Cartoon rendering took too long. Retry with a shorter video.", category="CARTOON_RENDER_TIMEOUT") from exc
    return int(proc.returncode or 0), (stdout + b"\n" + stderr).decode("utf-8", errors="replace")[-6000:]


def _engine_paths() -> tuple[Path, Path, Path]:
    backend = Path(__file__).resolve().parents[2]
    engine = backend / "cartoon_engine"
    cli = engine / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    gsap = engine / "node_modules" / "gsap" / "dist" / "gsap.min.js"
    if not cli.is_file():
        cli = Path("/usr/local/lib/node_modules/hyperframes/bin/hyperframes.mjs")
    if not gsap.is_file():
        gsap = Path("/usr/local/lib/node_modules/gsap/dist/gsap.min.js")
    node = Path(shutil.which("node") or shutil.which("nodejs") or "")
    return engine, cli, gsap if node else Path("")


async def run_cartoon_generation(job: dict[str, Any], scratch: Path, storage) -> None:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    project_id = str(payload.get("cartoon_project_id") or "")
    if not project_id:
        raise CartoonJobError("Cartoon project reference is missing.", category="CARTOON_JOB_INVALID")
    project = await fetch_one("SELECT * FROM cartoon_projects WHERE id=? AND user_id=?", (project_id, job["user_id"]))
    if not project:
        raise CartoonJobError("This cartoon project no longer exists.", category="CARTOON_PROJECT_MISSING")
    if project.get("status") == "ready" and project.get("output_key"):
        await update_job(job["id"], 100, "ready", "Your cartoon is ready", "completed")
        return
    credential = await fetch_one(
        "SELECT api_key_ciphertext FROM cartoon_provider_credentials WHERE user_id=? AND provider='openrouter'",
        (job["user_id"],),
    )
    if not credential:
        raise CartoonJobError("Connect your OpenRouter API key in Cartoon Studio before generating a video.", category="CARTOON_PROVIDER_MISSING")
    try:
        api_key = decrypt_provider_key(str(credential["api_key_ciphertext"]))
    except Exception as exc:
        raise CartoonJobError("Reconnect your OpenRouter API key securely, then retry.", category="CARTOON_PROVIDER_AUTH") from exc

    await execute(
        "UPDATE cartoon_projects SET status='processing',progress=5,stage='preparing',error=NULL,updated_at=? WHERE id=?",
        (utcnow(), project_id),
    )
    await update_job(job["id"], 5, "preparing", "Preparing your cartoon story")
    project_dir = scratch / "cartoon" / project_id
    (project_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (project_dir / "uploads").mkdir(parents=True, exist_ok=True)

    storyboard = _loads(project.get("storyboard_json"), {})
    if not storyboard.get("scenes"):
        frames = await _extract_reference_frames(job, project, scratch, storage)
        await update_job(job["id"], 12, "story_planning", "GLM is writing the story and keeping characters consistent")
        storyboard = await _generate_storyboard(
            api_key, str(project["prompt"]), int(project["duration_seconds"]),
            str(project["style"]), str(project["language"]), frames,
        )
        await execute(
            "UPDATE cartoon_projects SET storyboard_json=?,progress=18,stage='story_ready',updated_at=? WHERE id=?",
            (json.dumps(storyboard, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id),
        )
    if str(project.get("style") or "") == "cinematic-jannat" and storyboard.get("schema_version") != 3:
        storyboard = _apply_cinematic_jannat_storyboard(storyboard)
        await execute(
            "UPDATE cartoon_projects SET storyboard_json=?,updated_at=? WHERE id=?",
            (json.dumps(storyboard, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id),
        )

    tts_model = str(project.get("tts_model") or "hexgrad/kokoro-82m")
    tts_models = await _openrouter_models(api_key, "speech")
    tts_models.append(system_urdu_tts_model_row())
    model_row = next((row for row in tts_models if row.get("id") == tts_model), None)
    if not model_row:
        raise CartoonJobError("The selected text-to-speech model is no longer available. Refresh the voice model list and retry.", category="CARTOON_TTS_MODEL_UNAVAILABLE")
    voices = [str(value) for value in (model_row.get("supported_voices") or []) if str(value)]
    if not voices:
        raise CartoonJobError(
            "The selected speech model no longer provides preset voices. Refresh the voice model list and retry.",
            category="CARTOON_TTS_VOICES_UNAVAILABLE",
        )
    for character in storyboard.get("characters", []):
        saved_voice = str(character.get("voice_id") or "")
        character["voice_id"] = saved_voice if saved_voice in voices else _voice_for(
            character, voices, str(project.get("language") or "auto").lower(),
        )

    # Persist the character-to-voice assignment before making any billable TTS
    # calls. Retries therefore keep the same character voice IDs.
    await execute(
        "UPDATE cartoon_projects SET storyboard_json=?,progress=18,stage='story_ready',updated_at=? WHERE id=?",
        (json.dumps(storyboard, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id),
    )
    if storyboard.get("schema_version") == 3:
        from app.services.cartoon_story_job import run_director_job
        try:
            return await run_director_job(job, project, storyboard, project_dir, storage, api_key, tts_model)
        except StoryValidationError as exc:
            raise CartoonJobError(str(exc), category="CARTOON_STORY_TIMELINE_INVALID") from exc
    assets = _loads(project.get("assets_json"), {})
    audio_assets: list[dict[str, Any]] = []
    cinematic_jannat = str(project.get("style") or "") == "cinematic-jannat"
    scenes = storyboard.get("scenes", [])
    for index, scene in enumerate(scenes):
        scene_id = str(scene["id"])
        filename = f"scene-{index+1}.mp3"
        local_audio = project_dir / "assets" / "audio" / filename
        saved = assets.get(scene_id) if isinstance(assets.get(scene_id), dict) else {}
        word_boundaries = saved.get("word_boundaries") if isinstance(saved.get("word_boundaries"), list) else []
        lip_envelope = saved.get("lip_envelope") if isinstance(saved.get("lip_envelope"), list) else []
        asset_generation = saved.get("generation")
        audio_key = str(saved.get("key") or f"users/{job['user_id']}/cartoons/{project_id}/audio/{filename}")
        audio_meta = await storage.stat(audio_key) if saved.get("key") else None
        if audio_meta and audio_meta.size > 0:
            await storage.download(audio_key, local_audio, generation=saved.get("generation"))
            audio_duration = float(saved.get("duration") or 0)
        else:
            character = next((item for item in storyboard["characters"] if item["id"] == scene["speaker_id"]), storyboard["characters"][0])
            voice_progress = 20 + int(index / max(1, len(scenes)) * 30)
            await execute(
                "UPDATE cartoon_projects SET progress=?,stage='voice_generation',updated_at=? WHERE id=?",
                (voice_progress, utcnow(), project_id),
            )
            await update_job(job["id"], voice_progress, "voice_generation", f"Generating {character['name']}'s voice \u00b7 scene {index+1} of {len(scenes)}")
            word_boundaries = await _tts_audio(
                api_key, tts_model, str(character.get("voice_id") or "Puck"),
                str(scene.get("dialogue") or ""), local_audio,
                rate="-18%" if cinematic_jannat else "-8%",
                volume="-12%" if cinematic_jannat else "-8%", pitch="-3Hz",
            )
            if tts_model == SYSTEM_URDU_TTS_MODEL:
                await asyncio.sleep(0.75)
            audio_duration = float((await probe_metadata(local_audio))["duration"]) if local_audio.suffix.lower() in {".mp4", ".mov"} else 0.0
            ffprobe = shutil.which("ffprobe")
            if ffprobe:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(local_audio)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
                )
                try:
                    audio_duration = float(proc.stdout.decode().strip())
                except ValueError:
                    audio_duration = max(1.5, len(str(scene.get("dialogue") or "").split()) * .36)
            else:
                audio_duration = max(1.5, len(str(scene.get("dialogue") or "").split()) * .36)
            uploaded = await storage.upload(local_audio, audio_key, content_type="audio/mpeg")
            asset_generation = uploaded.generation
            assets[scene_id] = {"key": audio_key, "generation": uploaded.generation, "duration": audio_duration, "word_boundaries": word_boundaries}
            await execute(
                "UPDATE cartoon_projects SET assets_json=?,updated_at=? WHERE id=?",
                (json.dumps(assets, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id),
            )
        if not lip_envelope:
            lip_envelope = await build_lip_envelope(local_audio)
        assets[scene_id] = {
            "key": audio_key,
            "generation": asset_generation,
            "duration": audio_duration,
            "word_boundaries": word_boundaries,
            "lip_envelope": lip_envelope,
        }
        await execute(
            "UPDATE cartoon_projects SET assets_json=?,updated_at=? WHERE id=?",
            (json.dumps(assets, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id),
        )
        slot = int(project["duration_seconds"]) / max(1, len(scenes))
        speech_start = 6.2 if cinematic_jannat and index == 0 else min(1.05, slot * .16)
        speaker_id = str(scene.get("speaker_id") or "")
        if word_boundaries:
            caption_words = normalize_word_boundaries(
                word_boundaries,
                audio_duration=audio_duration,
                global_start=speech_start,
                speaker_id=speaker_id,
                track="dialogue",
            )
        else:
            caption_words = approximate_word_boundaries(
                str(scene.get("dialogue") or ""),
                audio_duration=audio_duration,
                global_start=speech_start,
                speaker_id=speaker_id,
                track="dialogue",
            )
        audio_assets.append({
            "scene_id": scene_id,
            "filename": filename,
            "duration": audio_duration,
            "words": caption_words,
            "word_boundaries": word_boundaries,
            "lip_envelope": lip_envelope,
            "speaker_id": speaker_id,
            "speech_start_seconds": speech_start,
        })
    storyboard_json = json.dumps(storyboard, separators=(",", ":"), ensure_ascii=False)
    await execute(
        "UPDATE cartoon_projects SET storyboard_json=?,progress=60,stage='animating',updated_at=? WHERE id=?",
        (storyboard_json, utcnow(), project_id),
    )
    await update_job(job["id"], 60, "animating", "Building character rigs, scenes and dialogue animation")

    engine, cli, gsap = _engine_paths()
    node = shutil.which("node") or shutil.which("nodejs")
    animation_bundle = engine / "dist" / "animation.js"
    if not node or not cli.is_file() or not gsap.is_file() or not animation_bundle.is_file():
        raise CartoonJobError(
            "The cartoon renderer is missing from the media worker. Deploy the updated media image.",
            category="CARTOON_RENDERER_UNAVAILABLE",
        )
    shutil.copy2(gsap, project_dir / "assets" / "gsap.min.js")
    shutil.copy2(animation_bundle, project_dir / "assets" / "animation.js")

    render_project = {**project, "native_animation": True}
    if cinematic_jannat:
        if str(project.get("aspect_ratio") or "") != "16:9" or int(project.get("duration_seconds") or 0) != 30:
            raise CartoonJobError(
                "The Jannat cinematic reference preset currently requires 30 seconds in 16:9 format.",
                category="CARTOON_CINEMATIC_PRESET_INVALID",
            )
        episode_lip_envelope = build_episode_lip_envelope(
            audio_assets,
            total_duration=30,
            slot_seconds=int(project["duration_seconds"]) / len(scenes),
        )
        audio_dir = project_dir / "assets" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        for audio_asset in audio_assets:
            scene_id = str(audio_asset.get("scene_id") or "scene")
            (audio_dir / f"{scene_id}-words.json").write_text(
                json.dumps(audio_asset.get("word_boundaries") or [], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (audio_dir / "dialogue-words.json").write_text(
            json.dumps([
                {
                    "scene_id": item.get("scene_id"),
                    "speech_start_seconds": item.get("speech_start_seconds"),
                    "word_boundaries": item.get("word_boundaries") or [],
                }
                for item in audio_assets
            ], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (audio_dir / "episode-lip-envelope.json").write_text(
            json.dumps({"fps": 60, "samples": episode_lip_envelope}, separators=(",", ":")),
            encoding="utf-8",
        )
        render_project["episode_lip_envelope"] = episode_lip_envelope
        await update_job(job["id"], 66, "audio_mixing", "Generating Urdu narration, original suspense score and bedroom foley")
        audio_dir = project_dir / "assets" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        narration_text = str(storyboard.get("narration") or "").strip()
        if not narration_text:
            narration_text = "\u0622\u062f\u06be\u06cc\u0020\u0631\u0627\u062a\u0020\u06a9\u0648\u060c\u0020\u062c\u0646\u062a\u0020\u0627\u06cc\u06a9\u0020\u0628\u0627\u0631\u0020\u067e\u06be\u0631\u0020\u0627\u0633\u06cc\u0020\u062e\u0648\u0627\u0628\u0020\u0633\u06d2\u0020\u062c\u0627\u06af\u0020\u0627\u0679\u06be\u06cc\u06d4"
        narration_path = audio_dir / "narration.mp3"
        narration_key = f"users/{job['user_id']}/cartoons/{project_id}/audio/narration.mp3"
        saved_narration = assets.get("_narration") if isinstance(assets.get("_narration"), dict) else {}
        narration_meta = await storage.stat(narration_key) if saved_narration.get("key") else None
        if narration_meta and narration_meta.size > 0:
            await storage.download(narration_key, narration_path, generation=saved_narration.get("generation"))
            narration_boundaries = saved_narration.get("word_boundaries") if isinstance(saved_narration.get("word_boundaries"), list) else []
            narration_duration = float(saved_narration.get("duration") or 0)
        else:
            narrator = storyboard["characters"][0]
            narration_boundaries = await _tts_audio(
                api_key, tts_model, str(narrator.get("voice_id") or "ur-PK-UzmaNeural"),
                narration_text, narration_path, rate="-8%", volume="-8%", pitch="-3Hz",
            )
            narration_duration = await _probe_audio_duration(narration_path)
            await asyncio.sleep(0.75)
            uploaded_narration = await storage.upload(narration_path, narration_key, content_type="audio/mpeg")
            assets["_narration"] = {
                "key": narration_key,
                "generation": uploaded_narration.generation,
                "duration": narration_duration,
                "word_boundaries": narration_boundaries,
            }
            await execute(
                "UPDATE cartoon_projects SET assets_json=?,updated_at=? WHERE id=?",
                (json.dumps(assets, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id),
            )
        if narration_duration <= 0:
            narration_duration = await _probe_audio_duration(narration_path)
        narration_words = normalize_word_boundaries(
            narration_boundaries, audio_duration=narration_duration,
            global_start=0.4, speaker_id="narrator", track="narration",
        )
        (audio_dir / "narration-words.json").write_text(
            json.dumps(narration_boundaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        jannat_voice = str(storyboard["characters"][0].get("voice_id") or "ur-PK-UzmaNeural")
        (audio_dir / "voice-info.json").write_text(
            json.dumps({
                "provider": "Microsoft Edge speech service via edge-tts",
                "language": "ur-PK",
                "voice_id": jannat_voice,
                "narration": {"rate": "-8%", "volume": "-8%", "pitch": "-3Hz"},
                "dialogue": {"rate": "-18%", "volume": "-12%", "pitch": "-3Hz"},
                "timing": "Native Edge TTS WordBoundary events (100 ns ticks)",
                "note": "External speech service; availability and commercial-use terms must be reviewed.",
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        stems = await asyncio.to_thread(build_jannat_audio_stems, audio_dir, duration_seconds=30)
        render_project["narration_words"] = narration_words
        render_project["audio_tracks"] = [
            {
                "track": "narration", "filename": narration_path.name,
                "start_seconds": 0.4, "duration_seconds": narration_duration,
                "volume": 1.0, "fade_in_seconds": 0.05, "fade_out_seconds": 0.15,
            },
            {
                "track": "music", "filename": Path(stems["score_path"]).name,
                "start_seconds": 0.0, "duration_seconds": 30.0,
                "volume": 0.75, "fade_in_seconds": 0.0, "fade_out_seconds": 0.0,
            },
            {
                "track": "foley", "filename": Path(stems["foley_path"]).name,
                "start_seconds": 0.0, "duration_seconds": 30.0,
                "volume": 1.0, "fade_in_seconds": 0.0, "fade_out_seconds": 0.0,
            },
        ]
    render_files = build_cartoon_project(render_project, storyboard, audio_assets)
    for relative_path, content in render_files.items():
        target_path = project_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": True},
    }, indent=2), encoding="utf-8")
    (project_dir / "meta.json").write_text(json.dumps({
        "id": project_id, "name": str(storyboard.get("title") or "ClipKaro Cartoon"),
    }, indent=2), encoding="utf-8")
    env = os.environ.copy()
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if chromium:
        env.setdefault("PUPPETEER_EXECUTABLE_PATH", chromium)
    else:
        env.pop("PUPPETEER_EXECUTABLE_PATH", None)
    headless_path_file = Path("/etc/hyperframes-headless-shell-path")
    if headless_path_file.is_file():
        headless_path = headless_path_file.read_text(encoding="utf-8").strip()
        if headless_path:
            env["PRODUCER_HEADLESS_SHELL_PATH"] = headless_path
    await execute(
        "UPDATE cartoon_projects SET progress=68,stage='checking',updated_at=? WHERE id=?",
        (utcnow(), project_id),
    )
    await update_job(job["id"], 68, "checking", "Checking the animation before rendering")
    check_code, check_output = await _run_cli([node, str(cli), "check", "--json"], cwd=project_dir, env=env, timeout=180)
    if check_code != 0:
        logger.warning("cartoon_hyperframes_check_failed project_id=%s", project_id)
        raise CartoonJobError("The cartoon composition did not pass its render checks. Please retry; the saved storyboard and voices are safe.", category="CARTOON_RENDER_CHECK_FAILED")
    await execute(
        "UPDATE cartoon_projects SET progress=76,stage='rendering',updated_at=? WHERE id=?",
        (utcnow(), project_id),
    )
    await update_job(job["id"], 76, "rendering", "Rendering your cartoon video")
    output = project_dir / "final.mp4"
    render_code, render_output = await _run_cli(
        [node, str(cli), "render", "--quality", "high", "--workers", "1", "--low-memory-mode", "-o", str(output)],
        cwd=project_dir, env=env, timeout=900,
    )
    if render_code != 0 or not output.is_file() or output.stat().st_size < 10_000:
        logger.warning("cartoon_hyperframes_render_failed project_id=%s exit=%s", project_id, render_code)
        raise CartoonJobError("The cartoon renderer could not finish this video. Your storyboard and voice files are saved; retry rendering.", category="CARTOON_RENDER_FAILED")
    metadata = await probe_metadata(output)
    expected = int(project["duration_seconds"])
    if abs(float(metadata["duration"]) - expected) > 1.6:
        raise CartoonJobError("The rendered video duration did not match the requested length. Retry the render.", category="CARTOON_RENDER_DURATION_INVALID")
    await execute(
        "UPDATE cartoon_projects SET progress=94,stage='uploading',updated_at=? WHERE id=?",
        (utcnow(), project_id),
    )
    await update_job(job["id"], 94, "uploading", "Saving your finished cartoon")
    output_key = f"users/{job['user_id']}/cartoons/{project_id}/final.mp4"
    stored = await storage.upload(output, output_key, content_type="video/mp4")
    await execute(
        """UPDATE cartoon_projects SET status='ready',progress=100,stage='ready',output_key=?,
           output_generation=?,error=NULL,storyboard_json=?,assets_json=?,updated_at=? WHERE id=?""",
        (
            output_key, stored.generation, storyboard_json,
            json.dumps(assets, separators=(",", ":"), ensure_ascii=False), utcnow(), project_id,
        ),
    )
    await update_job(job["id"], 100, "ready", "Your cartoon is ready to download", "completed")

"""Shared V3 story planner for the worker and the internal storyboard test."""
from __future__ import annotations

import asyncio
import base64
import copy
import json
import logging
import re
from pathlib import Path

import httpx

from .cartoon_story import DialogueSpeakerError, StoryValidationError, director_prompt, director_response_schema, normalize_director_story, prepare_director_reply
from .cartoon_story_direction import direct_story, scripted_scene_lengths

OPENROUTER_ROOT = "https://openrouter.ai/api/v1"
NVIDIA_ROOT = "https://integrate.api.nvidia.com/v1"
STORY_MODEL = "z-ai/glm-5.3-flash"
FREE_STORY_MODEL = "inclusionai/ling-3.2-flash:free"
NVIDIA_STORY_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
PROJECT_STORY_MODELS = {
    "glm": STORY_MODEL,
    "free": FREE_STORY_MODEL,
    "nvidia": NVIDIA_STORY_MODEL,
}
STORY_COMPLETION_TOKENS = 16_384
REPAIRABLE_STORYBOARD_ERRORS = frozenset({
    "CARTOON_STORY_BEAT_TIMING", "CARTOON_STORY_DIALOGUE_SPEAKER",
    "CARTOON_STORY_TRUNCATED", "CARTOON_STORY_INVALID",
})
logger = logging.getLogger("clipkaro.cartoon")


class StoryboardReplyError(ValueError):
    def __init__(self, message: str, category: str = "CARTOON_STORY_INVALID"):
        super().__init__(message)
        self.category = category


def planner_payload(prompt: str, duration: int, style: str, language: str, *,
                    provider: str, frames: tuple[Path, ...] = (), model: str | None = None) -> dict:
    user_text = director_prompt(duration, language, style, prompt)
    lengths = scripted_scene_lengths(prompt, duration)
    if lengths:
        user_text += (
            f"\nThe user's script specifies {len(lengths)} consecutive time ranges. Return exactly "
            f"{len(lengths)} scenes in order with durations {list(lengths)} seconds. Each scene must "
            "contain only the action, dialogue and sound from its own range. Keep scene-local timestamps "
            "and repeat the setting across scenes when the location stays the same."
        )
    nvidia = provider == "nvidia"
    schema = director_response_schema()
    if nvidia or model == FREE_STORY_MODEL:
        scenes = schema["properties"]["scenes"]
        scenes["maxItems"] = len(lengths) or min(12, max(3, (duration + 7) // 8))
        scenes["minItems"] = len(lengths) or 1
        schema["properties"]["characters"].update(minItems=1, maxItems=4)
        _limit_scene_detail(schema, compact=False)
        user_text += (
            "\nUse a short title and one-sentence summary. Keep each scene's data concise. "
            "Use one action per meaningful beat and one to three camera keys. "
            "Leave unused lists empty and avoid repeating actions or filling array limits."
        )
    content = user_text if nvidia else [
        {"type": "text", "text": user_text},
        *[{"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode("ascii")
        }} for frame in frames],
    ]
    return {
        "model": NVIDIA_STORY_MODEL if nvidia else (model or STORY_MODEL),
        "temperature": .65,
        "max_tokens": STORY_COMPLETION_TOKENS,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "clipkaro_storyboard", "strict": True, "schema": schema},
        },
        "messages": [
            {"role": "system", "content": (
                "You are ClipKaro's animation director. Return only a validated data storyboard, never code. "
                "Plan original characters, timed physical actions, cinematography, narration, dialogue and sound."
            )},
            {"role": "user", "content": content},
        ],
        **({"stream": False, "reasoning_effort": "none"} if nvidia else {
            "reasoning": {"effort": "none" if model == FREE_STORY_MODEL else "low", "exclude": True},
            "provider": {"require_parameters": True},
        }),
    }


async def request_storyboard(api_key: str, payload: dict, *, provider: str, timeout: int = 180) -> httpx.Response:
    root = NVIDIA_ROOT if provider == "nvidia" else OPENROUTER_ROOT
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(timeout), connect=15.0)) as client:
            response = await client.post(
                f"{root}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            return response


def _limit_scene_detail(schema: dict, *, compact: bool) -> None:
    properties = schema["properties"]["scenes"]["items"]["properties"]
    limits = {"character_ids": 4, "actors": 4, "props": 8, "actions": 14, "camera": 4, "speech": 8, "sounds": 8}
    if compact:
        limits.update(actions=8, camera=3, sounds=4)
    for field, limit in limits.items():
        properties[field]["maxItems"] = limit


def storyboard_correction_payload(payload: dict, category: str, validation_message: str = "") -> dict:
    system, idea = payload["messages"]
    guidance = {
        "CARTOON_STORY_DIALOGUE_SPEAKER": (
            "The first storyboard was rejected because a dialogue speaker was not visible in their scene. "
            "Use narrator only for narration. Use the speaker's exact ID, declare them in character_ids and actors, "
            "and give the visible actor a speak action at the line's start."
        ),
        "CARTOON_STORY_BEAT_TIMING": (
            "The first storyboard was rejected because its scene count did not match the explicit ranges. "
            "Make exactly one scene object for each requested range, including adjacent scenes in the same setting. "
            "Keep each line and action in its original range."
        ),
        "CARTOON_STORY_TRUNCATED": (
            "The first storyboard exceeded the output budget. Produce a compact, complete JSON object. "
            "Keep the key actions in each beat and remove repeated gestures, shots and sound cues."
        ),
        "CARTOON_STORY_INVALID": (
            "The first storyboard failed validation. Fix this issue: " + validation_message
        ),
    }[category]
    replacement = copy.deepcopy(payload)
    if category in {"CARTOON_STORY_TRUNCATED", "CARTOON_STORY_INVALID"}:
        _limit_scene_detail(replacement["response_format"]["json_schema"]["schema"], compact=True)
    guidance += " Return a complete replacement preserving the supplied script, timing, dialogue and ending."
    correction = {**system, "content": system["content"] + " " + guidance}
    return {**replacement, "temperature": .2, "messages": [correction, idea]}


def parse_storyboard_reply(response: httpx.Response, *, prompt: str, duration: int) -> dict:
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
                STORY_COMPLETION_TOKENS, completion if type(completion) is int else None,
                reasoning if type(reasoning) is int else None,
            )
            raise StoryboardReplyError(
                "The story planner ran out of space before finishing its storyboard.",
                "CARTOON_STORY_TRUNCATED",
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
        lengths = scripted_scene_lengths(prompt, duration)
        if lengths and isinstance(raw.get("scenes"), list) and len(raw["scenes"]) != len(lengths):
            raise StoryboardReplyError(
                f"The story planner combined or split your {len(lengths)} timed scenes. Retry to keep the scripted timing.",
                "CARTOON_STORY_BEAT_TIMING",
            )
        storyboard = normalize_director_story(
            prepare_director_reply(raw, prompt=prompt), duration=duration, scene_lengths=lengths,
        )
        return direct_story(storyboard, prompt)
    except StoryboardReplyError:
        raise
    except StoryValidationError as exc:
        logger.warning("Cartoon storyboard rejected: %s", exc)
        category = "CARTOON_STORY_DIALOGUE_SPEAKER" if isinstance(exc, DialogueSpeakerError) else "CARTOON_STORY_INVALID"
        raise StoryboardReplyError(f"The story planner produced an unsupported storyboard. {exc}", category) from exc
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Cartoon planner response could not be read (%s)", type(exc).__name__)
        raise StoryboardReplyError("The story planner returned an unreadable response.") from exc

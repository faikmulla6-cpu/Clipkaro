import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from .clip_finder import candidate_clips, find_clips, overlap_ratio

logger = logging.getLogger("clipkaro.semantic_ranking")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"


class GroqAuthError(RuntimeError):
    pass


class GroqRateLimitError(RuntimeError):
    pass


class GroqModelError(RuntimeError):
    pass


class GroqServiceError(RuntimeError):
    pass


RANKING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rankings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "semantic_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "hook": {"type": "number", "minimum": 0, "maximum": 100},
                    "clarity": {"type": "number", "minimum": 0, "maximum": 100},
                    "value": {"type": "number", "minimum": 0, "maximum": 100},
                    "emotion": {"type": "number", "minimum": 0, "maximum": 100},
                    "flow": {"type": "number", "minimum": 0, "maximum": 100},
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "candidate_id", "semantic_score", "hook", "clarity", "value",
                    "emotion", "flow", "title", "reason",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rankings"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are ClipKaro's semantic short-form video editor.
Rank ONLY the supplied transcript candidates; never invent missing context or facts.
Treat Hindi, Hinglish, Marathi and English equally well.
A strong short must work for a viewer who has not seen the original video.
Reward: an immediate hook, standalone clarity, a complete thought/payoff, useful or emotional value,
coherent flow, specificity, tension/revelation, and a satisfying ending.
Penalize: greetings/intros, filler, context-dependent fragments, repeated ideas, weak openings,
unfinished endings, vague claims, and setup with no payoff.
The score is editorial quality for short-form selection, NOT a guaranteed virality probability.
Keep titles factual and concise. Reasons must refer only to evidence present in that candidate.
Return one ranking object for every supplied candidate_id."""


async def probe_groq_readiness() -> dict[str, Any]:
    """Read-only provider probe for the isolated worker; returns no keys or provider bodies."""
    settings = get_settings()
    if not settings.groq_ranking_enabled:
        return {"enabled": False, "configured": False, "reachable": False, "models_available": False, "code": "disabled"}
    keys = settings.groq_keys
    models = settings.groq_ranking_models
    if not keys or not models:
        return {"enabled": True, "configured": False, "reachable": False, "models_available": False, "code": "unconfigured"}

    timeout = min(max(2.0, float(settings.preflight_network_timeout_seconds)),
                  max(2.0, float(settings.groq_ranking_timeout_seconds)))
    saw_provider = False
    for key in keys:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    GROQ_MODELS_URL,
                    headers={"Authorization": f"Bearer {key}"},
                )
        except (httpx.TimeoutException, httpx.RequestError):
            return {"enabled": True, "configured": True, "reachable": False, "models_available": False, "code": "unreachable"}
        saw_provider = True
        if response.status_code in {401, 403}:
            # Try another explicitly configured redundancy key; never return which key failed.
            continue
        if response.status_code == 429:
            return {"enabled": True, "configured": True, "reachable": True, "models_available": False, "code": "rate_limited"}
        if response.status_code >= 400:
            return {"enabled": True, "configured": True, "reachable": True, "models_available": False, "code": "provider_error"}
        try:
            payload = response.json()
            available = {str(item.get("id") or "") for item in payload.get("data", []) if isinstance(item, dict)}
        except Exception:
            return {"enabled": True, "configured": True, "reachable": True, "models_available": False, "code": "invalid_response"}
        selected_available = bool(available.intersection(models))
        return {
            "enabled": True, "configured": True, "reachable": True,
            "models_available": selected_available,
            "code": "ready" if selected_available else "models_unavailable",
        }
    return {
        "enabled": True, "configured": True, "reachable": saw_provider,
        "models_available": False, "code": "credentials_rejected",
    }


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "clipkaro_semantic_ranking",
            "strict": True,
            "schema": RANKING_SCHEMA,
        },
    }


def _candidate_payload(candidates: list[dict[str, Any]], language: str) -> str:
    compact = [
        {
            "candidate_id": item["id"],
            "start_seconds": round(float(item["start_time"]), 2),
            "end_seconds": round(float(item["end_time"]), 2),
            "duration_seconds": round(float(item["end_time"]) - float(item["start_time"]), 2),
            "local_evidence_score": float(item["score"]),
            "transcript": str(item["text"])[:2600],
        }
        for item in candidates
    ]
    return json.dumps(
        {
            "spoken_language": language,
            "instruction": "Compare all candidates against each other and rank their editorial quality.",
            "candidates": compact,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def _request_model(api_key: str, model: str, candidates: list[dict[str, Any]], language: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _candidate_payload(candidates, language)},
        ],
        "temperature": 0.1,
        "reasoning_effort": "low",
        "max_completion_tokens": 3200,
        "response_format": _response_format(),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.groq_ranking_timeout_seconds) as client:
            response = await client.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise GroqServiceError("Groq request failed") from exc

    if response.status_code in {401, 403}:
        raise GroqAuthError("Groq credential was rejected")
    if response.status_code == 429:
        # Do not rotate credentials to work around organization-level limits.
        raise GroqRateLimitError("Groq rate limit reached")
    if response.status_code in {400, 404, 422}:
        raise GroqModelError(f"Groq model/request rejected with HTTP {response.status_code}")
    if response.status_code >= 500:
        raise GroqServiceError(f"Groq service returned HTTP {response.status_code}")
    if response.status_code >= 400:
        raise GroqServiceError(f"Groq request returned HTTP {response.status_code}")

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GroqServiceError("Groq returned an unreadable ranking payload") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("rankings"), list):
        raise GroqServiceError("Groq ranking payload did not match the expected schema")
    return parsed


async def _groq_rankings(candidates: list[dict[str, Any]], language: str) -> tuple[list[dict[str, Any]], str] | None:
    settings = get_settings()
    keys = settings.groq_keys
    models = settings.groq_ranking_models
    if not settings.groq_ranking_enabled or not keys or not models:
        return None

    key_index = 0
    while key_index < len(keys):
        key = keys[key_index]
        key_rejected = False
        for model in models:
            try:
                payload = await _request_model(key, model, candidates, language)
                return payload["rankings"], model
            except GroqAuthError:
                # A revoked/mistyped key may fail over to the next configured key.
                # Never log the credential itself.
                logger.warning("Groq credential slot %s was rejected; trying the next configured slot", key_index + 1)
                key_rejected = True
                break
            except GroqRateLimitError:
                # Groq limits are organization-level. Switching keys here would
                # be ineffective at best and quota circumvention at worst.
                raise
            except GroqModelError as exc:
                logger.warning("Groq ranking model %s unavailable (%s); trying model fallback", model, exc)
                continue
            except GroqServiceError as exc:
                logger.warning("Groq ranking model %s failed (%s); trying model fallback", model, exc)
                continue
        if key_rejected:
            key_index += 1
            continue
        # Both production model choices failed with a valid credential/service;
        # additional keys should not create duplicate traffic to the same outage.
        break
    return None


def _clean_text(value: Any, fallback: str, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    return (text or fallback)[:limit]


def _blend_candidates(candidates: list[dict[str, Any]], rankings: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_id = {
        str(item.get("candidate_id")): item
        for item in rankings
        if isinstance(item, dict) and item.get("candidate_id")
    }
    reranked: list[dict[str, Any]] = []
    matched = 0
    for candidate in candidates:
        semantic = by_id.get(str(candidate["id"]))
        enriched = dict(candidate)
        if semantic:
            try:
                semantic_score = max(0.0, min(float(semantic["semantic_score"]), 100.0))
                local_score = float(candidate["score"])
                enriched["score"] = round((semantic_score * .70) + (local_score * .30), 1)
                old_breakdown = candidate["score_breakdown"]
                enriched["score_breakdown"] = {
                    key: round(
                        max(0.0, min(100.0,
                            float(semantic[key]) * .68 + float(old_breakdown.get(key, 50.0)) * .32
                        )), 1
                    )
                    for key in ("hook", "clarity", "value", "emotion", "flow")
                }
                enriched["title"] = _clean_text(semantic.get("title"), candidate["title"], 90)
                enriched["reason"] = _clean_text(semantic.get("reason"), candidate["reason"], 260)
                enriched["ranking_source"] = "groq"
                matched += 1
            except (KeyError, TypeError, ValueError):
                enriched["ranking_source"] = "local"
        else:
            enriched["ranking_source"] = "local"
        reranked.append(enriched)

    # A partial/misaligned response is less trustworthy than the deterministic
    # ranker, so fail closed rather than letting a malformed LLM answer reorder it.
    if matched < max(2, len(candidates) // 2):
        raise GroqServiceError("Groq did not rank enough known candidates")

    reranked.sort(key=lambda item: (float(item["score"]), float(item["score_breakdown"]["hook"])), reverse=True)
    selected: list[dict[str, Any]] = []
    for clip in reranked:
        if all(overlap_ratio(clip, existing) <= .5 for existing in selected):
            selected.append(clip)
        if len(selected) >= limit:
            break
    return selected


def _local_fallback(segments: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    clips = find_clips(segments, limit)
    for clip in clips:
        clip["ranking_source"] = "local"
    return clips


async def find_best_clips(segments: list[dict[str, Any]], language: str, limit: int = 8) -> list[dict[str, Any]]:
    """Use Groq for semantic judgment while preserving a deterministic fallback.

    Only a compact local candidate pool is sent to Groq. Transcription evidence,
    boundaries and final overlap enforcement remain under ClipKaro's control.
    """
    settings = get_settings()
    candidates = candidate_clips(segments, max(limit, settings.groq_ranking_candidates))
    if not candidates:
        return []
    if not settings.groq_ranking_enabled or not settings.groq_keys:
        return _local_fallback(segments, limit)

    try:
        result = await _groq_rankings(candidates, language)
        if not result:
            return _local_fallback(segments, limit)
        rankings, model = result
        clips = _blend_candidates(candidates, rankings, limit)
        logger.info("Semantic ranking completed model=%s candidates=%s selected=%s", model, len(candidates), len(clips))
        return clips
    except GroqRateLimitError:
        logger.warning("Groq semantic ranking rate-limited; using deterministic local ranking")
        return _local_fallback(segments, limit)
    except GroqServiceError as exc:
        logger.warning("Groq semantic ranking unavailable (%s); using deterministic local ranking", exc)
        return _local_fallback(segments, limit)

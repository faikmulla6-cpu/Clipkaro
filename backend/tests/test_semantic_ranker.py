import pytest

from app.core.config import get_settings
from app.services import semantic_ranker


SEGMENTS = [
    {"start": 0, "end": 12, "text": "Today I want to explain a useful idea."},
    {"start": 12, "end": 27, "text": "Most creators make this mistake because they start with too much context."},
    {"start": 27, "end": 44, "text": "The better approach is simple: show the result first, then explain how you got there."},
    {"start": 44, "end": 61, "text": "That one change makes the lesson easier to understand and much easier to remember."},
    {"start": 61, "end": 78, "text": "Now here is a second ordinary point about planning your next upload."},
]


def _ranking_payload(candidates, preferred_id=None):
    rankings = []
    for index, candidate in enumerate(candidates):
        preferred = candidate["id"] == preferred_id
        base = 96 if preferred else max(45, 78 - index)
        rankings.append({
            "candidate_id": candidate["id"],
            "semantic_score": base,
            "hook": base,
            "clarity": min(100, base + 1),
            "value": min(100, base + 2),
            "emotion": max(25, base - 20),
            "flow": min(100, base + 1),
            "title": "Semantic choice" if preferred else candidate["title"],
            "reason": "Complete standalone idea with a clear payoff.",
        })
    return {"rankings": rankings}


@pytest.mark.asyncio
async def test_no_groq_keys_uses_deterministic_local_fallback(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_keys", "")
    for index in range(1, 6):
        monkeypatch.setattr(settings, f"groq_api_key_{index}", "")
    clips = await semantic_ranker.find_best_clips(SEGMENTS, "en", 3)
    assert clips
    assert all(clip["ranking_source"] == "local" for clip in clips)


@pytest.mark.asyncio
async def test_semantic_response_can_reorder_local_candidates(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_keys", "key-one")
    monkeypatch.setattr(settings, "groq_ranking_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_ranking_fallback_model", "openai/gpt-oss-20b")

    async def fake_request(api_key, model, candidates, language):
        assert api_key == "key-one"
        assert language == "en"
        # Deliberately prefer the last candidate to prove Groq can change order.
        return _ranking_payload(candidates, candidates[-1]["id"])

    monkeypatch.setattr(semantic_ranker, "_request_model", fake_request)
    clips = await semantic_ranker.find_best_clips(SEGMENTS, "en", 3)
    assert clips[0]["ranking_source"] == "groq"
    assert clips[0]["title"] == "Semantic choice"


@pytest.mark.asyncio
async def test_rejected_key_fails_over_to_next_credential(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_keys", "bad-key,good-key")
    monkeypatch.setattr(settings, "groq_ranking_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_ranking_fallback_model", "openai/gpt-oss-20b")
    calls = []

    async def fake_request(api_key, model, candidates, language):
        calls.append((api_key, model))
        if api_key == "bad-key":
            raise semantic_ranker.GroqAuthError("rejected")
        return _ranking_payload(candidates)

    monkeypatch.setattr(semantic_ranker, "_request_model", fake_request)
    clips = await semantic_ranker.find_best_clips(SEGMENTS, "en", 2)
    assert clips and clips[0]["ranking_source"] == "groq"
    assert calls[0][0] == "bad-key"
    assert calls[1][0] == "good-key"


@pytest.mark.asyncio
async def test_rate_limit_does_not_rotate_across_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_keys", "key-one,key-two,key-three")
    calls = []

    async def fake_request(api_key, model, candidates, language):
        calls.append((api_key, model))
        raise semantic_ranker.GroqRateLimitError("limited")

    monkeypatch.setattr(semantic_ranker, "_request_model", fake_request)
    clips = await semantic_ranker.find_best_clips(SEGMENTS, "en", 2)
    assert clips and all(clip["ranking_source"] == "local" for clip in clips)
    assert len(calls) == 1
    assert calls[0][0] == "key-one"


@pytest.mark.asyncio
async def test_model_failure_uses_production_model_fallback(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_keys", "key-one")
    monkeypatch.setattr(settings, "groq_ranking_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_ranking_fallback_model", "openai/gpt-oss-20b")
    models = []

    async def fake_request(api_key, model, candidates, language):
        models.append(model)
        if model == "openai/gpt-oss-120b":
            raise semantic_ranker.GroqModelError("temporary model issue")
        return _ranking_payload(candidates)

    monkeypatch.setattr(semantic_ranker, "_request_model", fake_request)
    clips = await semantic_ranker.find_best_clips(SEGMENTS, "en", 2)
    assert clips and clips[0]["ranking_source"] == "groq"
    assert models == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


@pytest.mark.asyncio
async def test_partial_unknown_ids_fail_closed_to_local(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_keys", "key-one")

    async def fake_request(api_key, model, candidates, language):
        return {"rankings": [{
            "candidate_id": "not-a-real-candidate",
            "semantic_score": 100, "hook": 100, "clarity": 100, "value": 100,
            "emotion": 100, "flow": 100, "title": "Wrong", "reason": "Wrong",
        }]}

    monkeypatch.setattr(semantic_ranker, "_request_model", fake_request)
    clips = await semantic_ranker.find_best_clips(SEGMENTS, "en", 2)
    assert clips and all(clip["ranking_source"] == "local" for clip in clips)

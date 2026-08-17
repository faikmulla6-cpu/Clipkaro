from pathlib import Path

import httpx
import pytest

from app.services.candidate_asr_providers import SpeechmaticsASRProvider


@pytest.mark.asyncio
@pytest.mark.parametrize(("hint", "language"), [("hi", "hi"), ("mr", "mr"), ("hinglish", "hi")])
async def test_speechmatics_enhanced_batch_uses_real_word_timestamps(monkeypatch, tmp_path, hint, language):
    calls = []

    async def post(self, url, **kwargs):
        calls.append(("post", url, kwargs))
        return httpx.Response(201, json={"id": "job-1"}, request=httpx.Request("POST", url))

    async def get(self, url, **kwargs):
        calls.append(("get", url, kwargs))
        if url.endswith("/transcript"):
            return httpx.Response(200, json={"results": [{"type": "word", "start_time": 0.1, "end_time": 0.4, "alternatives": [{"content": "नमस्ते", "confidence": 0.98}]}]}, request=httpx.Request("GET", url))
        return httpx.Response(200, json={"job": {"status": "done"}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    audio = Path(tmp_path) / "sample.flac"; audio.write_bytes(b"fixture")
    result = await SpeechmaticsASRProvider("test-key").transcribe(audio, language_hint=hint, duration=1)

    submitted = calls[0][2]
    assert submitted["headers"]["Authorization"] == "Bearer test-key"
    config = submitted["data"]["config"]
    assert f'"language": "{language}"' in config
    assert '"operating_point": "enhanced"' in config
    assert result.text == "नमस्ते"
    # The shared ClipKaro normalizer retains provider timing and confidence,
    # while representing lexical content with its standard `text` key.
    assert result.segments[0]["words"] == [{"start": 0.1, "end": 0.4, "text": "नमस्ते", "confidence": 0.98}]

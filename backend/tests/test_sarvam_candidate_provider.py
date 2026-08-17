from pathlib import Path

import httpx
import pytest

from app.services.candidate_asr_providers import SarvamSaarasV3Provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language_hint", "expected_language", "expected_mode"),
    [("hi", "hi-IN", "verbatim"), ("mr", "mr-IN", "verbatim"), ("hinglish", "hi-IN", "codemix")],
)
async def test_sarvam_uses_documented_mode_and_keeps_phrase_timestamps(monkeypatch, tmp_path, language_hint, expected_language, expected_mode):
    observed = {}

    async def post(self, url, **kwargs):
        observed.update(kwargs["data"])
        assert kwargs["headers"]["api-subscription-key"] == "test-key"
        return httpx.Response(200, json={
            "transcript": "नमस्ते hello",
            "language_code": expected_language,
            "timestamps": {"words": ["नमस्ते hello"], "start_time_seconds": [0.2], "end_time_seconds": [1.4]},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    audio = Path(tmp_path) / "sample.flac"
    audio.write_bytes(b"not-decoded-in-unit-test")
    result = await SarvamSaarasV3Provider("test-key").transcribe(audio, language_hint=language_hint, duration=2.0)

    assert observed == {"model": "saaras:v3", "language_code": expected_language, "mode": expected_mode, "with_timestamps": "true"}
    assert result.text == "नमस्ते hello"
    assert result.segments[0]["start"] == 0.2
    assert result.segments[0]["end"] == 1.4
    assert result.segments[0]["words"] == []
    assert result.timestamp_quality == "provider_segment"

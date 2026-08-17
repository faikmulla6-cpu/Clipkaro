from pathlib import Path

import httpx
import pytest

from app.services.candidate_asr_providers import GNANI_TRANSCRIBE_URL, GnaniPrismaV25Provider


@pytest.mark.asyncio
async def test_gnani_hinglish_uses_direct_multipart_upload_without_synthetic_timing(monkeypatch, tmp_path):
    observed = {}

    async def post(self, url, **kwargs):
        observed["url"] = url
        observed["headers"] = kwargs["headers"]
        observed["data"] = kwargs["data"]
        return httpx.Response(
            200,
            json={"success": True, "request_id": "safe-request-id", "transcript": "नमस्ते meeting"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    audio = Path(tmp_path) / "sample.flac"
    audio.write_bytes(b"fixture")

    result = await GnaniPrismaV25Provider("test-key").transcribe(
        audio, language_hint="hinglish", duration=2.0, request_id="candidate-test"
    )

    assert observed["url"] == GNANI_TRANSCRIBE_URL
    assert observed["headers"] == {"X-API-Key-ID": "test-key", "X-Request-ID": "candidate-test"}
    assert observed["data"] == {
        "language_code": "hi-IN",
        "preferred_language": "hi-IN",
        "format": "transcribe",
        "itn_native_numerals": "false",
    }
    assert result.provider == "gnani"
    assert result.model == "prisma-v2.5"
    assert result.text == "नमस्ते meeting"
    assert result.segments == []
    assert result.timestamp_quality == "unavailable"


@pytest.mark.asyncio
async def test_gnani_rejects_empty_or_explicitly_unsuccessful_responses(monkeypatch, tmp_path):
    responses = [{"success": False}, {"success": True, "transcript": ""}]

    async def post(self, url, **kwargs):
        return httpx.Response(200, json=responses.pop(0), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    audio = Path(tmp_path) / "sample.flac"
    audio.write_bytes(b"fixture")
    provider = GnaniPrismaV25Provider("test-key")

    from app.services.asr_providers import ASRProviderError

    with pytest.raises(ASRProviderError, match="rejected"):
        await provider.transcribe(audio, language_hint="hinglish", duration=2.0)
    with pytest.raises(ASRProviderError, match="empty"):
        await provider.transcribe(audio, language_hint="hinglish", duration=2.0)

import pytest
from pathlib import Path
from app.services.source_caption_detection import detect_burned_captions


@pytest.mark.asyncio
async def test_detector_fails_open_when_ocr_unavailable(monkeypatch):
    monkeypatch.setattr("app.services.source_caption_detection.shutil.which", lambda _: None)
    result = await detect_burned_captions(Path("missing.mp4"), 30)
    assert not result["detected"] and result["reason"] == "ocr_unavailable"

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from app.services.cartoon_speech import (
    SYSTEM_URDU_TTS_MODEL,
    system_urdu_tts_model_row,
    system_voice_for,
    synthesize_edge_tts,
)


def test_system_urdu_voice_mapping_and_model_descriptor():
    assert system_voice_for("ur", "female") == "ur-PK-UzmaNeural"
    assert system_voice_for("ur", "male") == "ur-PK-AsadNeural"
    row = system_urdu_tts_model_row()
    assert row["id"] == SYSTEM_URDU_TTS_MODEL
    assert row["name"] == "Built-in Urdu voices"
    assert "ur-PK-UzmaNeural" in row["supported_voices"]


def test_edge_tts_adapter_returns_native_word_boundaries(tmp_path, monkeypatch):
    class FakeCommunicate:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def stream(self):
            yield {"type": "audio", "data": b"x" * 256}
            yield {
                "type": "WordBoundary",
                "offset": 10_000_000,
                "duration": 5_000_000,
                "text": "hello",
            }

    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=FakeCommunicate))
    output = tmp_path / "voice.mp3"
    words = asyncio.run(synthesize_edge_tts("hello", "ur-PK-UzmaNeural", output, attempts=1))
    assert output.is_file()
    assert output.stat().st_size == 256
    assert words == [{
        "type": "WordBoundary",
        "offset": 10_000_000,
        "duration": 5_000_000,
        "text": "hello",
    }]

from __future__ import annotations

import hashlib
import wave

from app.services.cartoon_score import build_jannat_audio_stems


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_jannat_score_and_foley_are_deterministic_editable_48khz_stereo_wav(tmp_path):
    first = build_jannat_audio_stems(tmp_path / "first")
    second = build_jannat_audio_stems(tmp_path / "second")

    assert first["duration_seconds"] == 30
    assert first["sample_rate"] == 48_000
    assert first["score_path"].name == "score.wav"
    assert first["foley_path"].name == "foley.wav"
    assert _sha256(first["score_path"]) == _sha256(second["score_path"])
    assert _sha256(first["foley_path"]) == _sha256(second["foley_path"])
    assert _sha256(first["score_path"]) != _sha256(first["foley_path"])

    for path in (first["score_path"], first["foley_path"]):
        with wave.open(str(path), "rb") as audio:
            assert audio.getnchannels() == 2
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 48_000
            assert audio.getnframes() == 30 * 48_000

    metadata = (first["score_path"].parent / "audio-stems.json").read_text(encoding="utf-8")
    assert "original procedural audio" in metadata.lower()

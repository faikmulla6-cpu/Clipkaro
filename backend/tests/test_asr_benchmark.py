from __future__ import annotations

import importlib.util
import math
import struct
import wave
from pathlib import Path

import pytest

from app.services.asr_benchmark import (
    STRESS_SCENARIOS,
    create_stress_variant,
    error_rate,
    expected_language_matches,
    language_family,
    normalize_text,
    percentile,
    probe_duration,
    summarize_results,
    validate_timestamps,
)
from app.services.asr_negative_controls import NEGATIVE_CONTROLS, create_negative_control


def _tone(path: Path, seconds: float = 3.0, frequency: float = 440.0) -> None:
    sample_rate = 16000
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frames):
            value = int(9000 * math.sin(2 * math.pi * frequency * index / sample_rate))
            wav.writeframesraw(struct.pack("<h", value))


def _load_script_module(script_name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"clipkaro_test_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_text_normalization_and_error_rates_support_indic_script() -> None:
    assert normalize_text("  नमस्ते, WORLD!  ") == "नमस्ते world"
    assert error_rate("hello world", "hello world") == 0
    assert error_rate("hello world", "hello there") == pytest.approx(0.5)
    assert error_rate("नमस्ते दुनिया", "नमस्ते दुनियां", unit="char") > 0


def test_percentile_is_interpolated_and_empty_is_fail_closed() -> None:
    assert percentile([0.1, 0.2, 0.3], 0.5) == pytest.approx(0.2)
    assert percentile([], 0.9) == math.inf


def test_language_matching_handles_hindi_marathi_and_hinglish() -> None:
    assert language_family("Hindi") == "hi"
    assert language_family("Marathi") == "mr"
    assert language_family("hi-en") == "hinglish"
    assert expected_language_matches("hi", "hi")
    assert expected_language_matches("Hindi", "hi")
    assert expected_language_matches("mr", "mr")
    assert expected_language_matches("Marathi", "mr")
    assert expected_language_matches("hinglish", "hi")
    assert expected_language_matches("hi-en", "en")
    assert not expected_language_matches("mr", "hi")


def test_timestamp_validation_rejects_collapsed_and_out_of_bounds_words() -> None:
    valid = validate_timestamps([
        {
            "start": 1.0,
            "end": 3.0,
            "text": "hello world",
            "words": [
                {"start": 1.0, "end": 1.4, "text": "hello"},
                {"start": 1.5, "end": 2.0, "text": "world"},
            ],
        }
    ], 5.0)
    assert valid["valid"] is True

    broken = validate_timestamps([
        {
            "start": 1.0,
            "end": 3.0,
            "text": "bad timing",
            "words": [
                {"start": 1.0, "end": 1.0, "text": "bad"},
                {"start": 4.0, "end": 4.3, "text": "timing"},
            ],
        }
    ], 3.2)
    assert broken["valid"] is False
    assert any("collapsed" in issue for issue in broken["issues"])
    assert any("outside_segment" in issue for issue in broken["issues"])


def _passing_rows(per_family: int = 3) -> list[dict]:
    rows = []
    for scenario in STRESS_SCENARIOS:
        for family in ("hi", "mr", "hinglish"):
            for index in range(per_family):
                rows.append({
                    "case_id": f"{scenario.name}-{family}-{index}",
                    "language": family,
                    "scenario": scenario.name,
                    "wer": min(0.10 + index * 0.002, scenario.max_p90_wer / 2),
                    "cer": min(0.06 + index * 0.001, scenario.max_p90_cer / 2),
                    "rtf": min(0.5 + index * 0.01, scenario.max_p95_rtf / 2),
                    "language_match": True,
                    "timestamps_valid": True,
                })
    return rows


def test_summary_requires_every_scenario_and_all_failure_budgets() -> None:
    passing = summarize_results(_passing_rows())
    assert passing["passed"] is True
    assert all(item["passed"] for item in passing["scenarios"].values())
    assert all(
        language["passed"]
        for scenario in passing["scenarios"].values()
        for language in scenario["by_language"].values()
    )

    missing = summarize_results([row for row in _passing_rows() if row["scenario"] != "street_noise"])
    assert missing["passed"] is False
    assert missing["scenarios"]["street_noise"]["reason"] == "no_results"

    bad = _passing_rows()
    for row in bad:
        if row["scenario"] == "fast_145":
            row["wer"] = 0.95
    failed = summarize_results(bad)
    assert failed["passed"] is False
    assert failed["scenarios"]["fast_145"]["passed"] is False


def test_one_weak_language_cannot_be_hidden_by_strong_aggregate() -> None:
    rows = _passing_rows(per_family=10)
    marathi_clean = [
        row for row in rows
        if row["scenario"] == "clean" and row["language"] == "mr"
    ]
    # Two severe Marathi misses are <10% of the combined 30 clean rows, so the
    # aggregate p90 stays healthy. Per-language gating must still fail Marathi.
    marathi_clean[-1]["wer"] = 0.95
    marathi_clean[-2]["wer"] = 0.95
    marathi_clean[-1]["cer"] = 0.75
    marathi_clean[-2]["cer"] = 0.75

    summary = summarize_results(rows)
    clean = summary["scenarios"]["clean"]
    assert clean["aggregate_passed"] is True
    assert clean["by_language"]["mr"]["passed"] is False
    assert clean["passed"] is False
    assert summary["passed"] is False


def test_asr_rejections_count_against_success_rate() -> None:
    rows = _passing_rows()
    clean_rows = [row for row in rows if row["scenario"] == "clean"]
    clean_rows[0]["error"] = "RuntimeError: rejected"
    summary = summarize_results(rows)
    assert summary["passed"] is False
    assert summary["scenarios"]["clean"]["success_rate"] < 0.95


def test_every_audio_corruption_recipe_produces_readable_media(tmp_path: Path) -> None:
    source = tmp_path / "speech.wav"
    street = tmp_path / "street.wav"
    _tone(source, frequency=440)
    _tone(street, frequency=95)

    for scenario in STRESS_SCENARIOS:
        output = tmp_path / f"{scenario.name}.m4a"
        create_stress_variant(
            source,
            output,
            scenario.name,
            street_noise=street if scenario.requires_street_noise else None,
        )
        assert output.exists()
        assert output.stat().st_size > 1024
        assert probe_duration(output) > 0.5


def test_negative_controls_produce_nonspeech_media(tmp_path: Path) -> None:
    for kind in NEGATIVE_CONTROLS:
        output = tmp_path / f"negative-{kind}.m4a"
        create_negative_control(output, kind, seconds=5.0)
        assert output.exists()
        assert output.stat().st_size > 1024
        assert probe_duration(output) >= 4.8


def test_mucs_kaldi_parser_resolves_slices_and_builds_hinglish_case(tmp_path: Path) -> None:
    mucs = _load_script_module("import_mucs_hinglish_corpus.py")
    root = tmp_path / "mucs"
    data_dir = root / "Hindi-English" / "data" / "test"
    audio_dir = root / "Hindi-English" / "audio"
    data_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)

    recording = audio_dir / "tutorial-01.wav"
    _tone(recording, seconds=7.0, frequency=260)
    (data_dir / "wav.scp").write_text(
        "tutorial-01 /upstream/machine/path/tutorial-01.wav\n",
        encoding="utf-8",
    )
    (data_dir / "segments").write_text(
        "utt-001 tutorial-01 0.00 2.00\n"
        "utt-002 tutorial-01 2.00 4.10\n"
        "utt-003 tutorial-01 4.10 6.50\n",
        encoding="utf-8",
    )
    (data_dir / "text").write_text(
        "utt-001 आज हम Python function सीखेंगे\n"
        "utt-002 यह दूसरा clean segment है\n"
        "utt-003 अब API response check करेंगे\n",
        encoding="utf-8",
    )

    assert mucs._find_kaldi_dirs(root) == [data_dir]
    assert mucs._read_kaldi_text(data_dir / "text")["utt-001"].startswith("आज")
    assert mucs._read_kaldi_segments(data_dir / "segments")[0]["duration"] == pytest.approx(2.0)
    assert mucs._wav_scp_path_tokens("sox /old/tutorial-01.wav -t wav - |") == ["/old/tutorial-01.wav"]
    assert mucs._is_code_switched("आज Python सीखेंगे") is True
    assert mucs._is_code_switched("आज हम सीखेंगे") is False

    utterances = mucs._load_kaldi_utterances(root)
    assert len(utterances) == 3
    assert utterances[0]["code_switched"] is True
    assert Path(utterances[0]["recording"]) == recording.resolve()

    sliced = tmp_path / "slice.wav"
    mucs._materialize_segment(utterances[0], sliced)
    assert 1.8 <= probe_duration(sliced) <= 2.2

    output_dir = tmp_path / "corpus"
    workdir = tmp_path / "work"
    workdir.mkdir()
    cases = mucs._build_cases(utterances, output_dir, cases=1, min_seconds=5.0, workdir=workdir)
    assert len(cases) == 1
    assert cases[0]["language"] == "hinglish"
    assert cases[0]["language_hint"] == "auto"
    assert cases[0]["explicit_code_switched_utterances"] >= 2
    assert cases[0]["source_utterances"] == 3
    assert probe_duration(output_dir / cases[0]["path"]) >= 5.0


def test_standalone_asr_qualification_scripts_compile() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    for script_name in (
        "asr_stress_benchmark.py",
        "asr_concurrency_soak.py",
        "fetch_fleurs_stress_corpus.py",
        "fetch_public_asr_noise_pack.py",
        "import_mucs_hinglish_corpus.py",
    ):
        path = backend_root / "scripts" / script_name
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

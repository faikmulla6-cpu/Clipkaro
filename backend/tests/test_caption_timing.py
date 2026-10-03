import pytest

from app.services.caption_timing import clip_speech_regions, reconcile_caption_words, speech_regions_from_segments


def test_reconcile_clamps_asr_tail_to_real_speech_end():
    regions = [{"start": 0.10, "end": 1.00}, {"start": 1.24, "end": 2.00}]
    words = [
        {"start": 0.30, "end": 1.18, "text": "designate", "confidence": .9},
        {"start": 1.28, "end": 1.55, "text": "place", "confidence": .9},
    ]
    gated = reconcile_caption_words(words, regions, 0.0, 2.0)
    assert gated[0]["end"] == pytest.approx(1.00)
    assert gated[0]["speech_region_id"] == 0
    assert gated[1]["speech_region_id"] == 1


def test_reconcile_does_not_drop_word_when_vad_has_no_overlap():
    regions = [{"start": 0.0, "end": 0.4}]
    words = [{"start": 0.8, "end": 1.0, "text": "quiet", "confidence": .5}]
    gated = reconcile_caption_words(words, regions, 0.0, 1.2)
    assert [word["text"] for word in gated] == ["quiet"]
    assert gated[0]["start"] == pytest.approx(.8)
    assert "speech_region_id" not in gated[0]


def test_clip_speech_regions_are_relative_and_keep_source_ids():
    segments = [{"speech_regions": [
        {"start": 10.0, "end": 10.8},
        {"start": 11.2, "end": 12.0},
    ]}]
    assert speech_regions_from_segments(segments) == [
        {"start": 10.0, "end": 10.8},
        {"start": 11.2, "end": 12.0},
    ]
    clipped = clip_speech_regions(segments, 10.5, 11.5)
    assert clipped == [
        {"id": 0, "start": 0.0, "end": .3},
        {"id": 1, "start": .7, "end": 1.0},
    ]


def test_words_bridge_only_inside_same_speech_region():
    regions = [{"start": 0.0, "end": 1.0}, {"start": 1.2, "end": 2.0}]
    words = [
        {"start": 0.10, "end": 0.30, "text": "one"},
        {"start": 0.50, "end": 0.70, "text": "two"},
        {"start": 1.30, "end": 1.50, "text": "three"},
    ]
    gated = reconcile_caption_words(words, regions, 0.0, 2.0)
    assert gated[0]["end"] == pytest.approx(.50)
    assert gated[1]["end"] == pytest.approx(.70)
    assert gated[1]["speech_region_id"] == 0
    assert gated[2]["speech_region_id"] == 1

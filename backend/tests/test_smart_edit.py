import pytest

from app.services.rendering import smart_edit_filter_complex
from app.services.smart_edit import apply_plan_to_words, clean_speech_ranges, kept_ranges, normalize_edit_plan, plan_reorders_segments


def test_plan_merges_overlaps_and_preserves_split_points():
    plan = normalize_edit_plan({
        "removed_ranges": [
            {"start": 1, "end": 2, "reason": "word"},
            {"start": 1.8, "end": 3, "reason": "silence"},
        ],
        "split_points": [4, 4.01, 8],
    }, 10)
    assert plan["removed_ranges"] == [{"start": 1.0, "end": 3.0, "reason": "mixed"}]
    assert plan["split_points"] == [4.0, 8.0]
    assert kept_ranges(plan, 10) == [{"start": 0.0, "end": 1.0}, {"start": 3.0, "end": 10}]


def test_removed_word_and_later_caption_are_retimed_together():
    words = [
        {"start": 0.0, "end": .4, "text": "keep"},
        {"start": .5, "end": 1.0, "text": "um"},
        {"start": 1.5, "end": 2.0, "text": "going"},
    ]
    plan = normalize_edit_plan({"removed_ranges": [{"start": .5, "end": 1.5, "reason": "clean"}]}, 2)
    edited = apply_plan_to_words(words, plan, 2)
    assert [item["text"] for item in edited] == ["keep", "going"]
    assert edited[1]["start"] == pytest.approx(.5)
    assert edited[1]["end"] == pytest.approx(1.0)


def test_clean_speech_finds_fillers_pauses_and_repeated_starts():
    words = [
        {"start": 0, "end": .2, "text": "I"},
        {"start": .25, "end": .45, "text": "I"},
        {"start": 1.0, "end": 1.2, "text": "um"},
        {"start": 1.25, "end": 1.6, "text": "agree"},
    ]
    ranges = clean_speech_ranges(words, 2)
    assert any(item["reason"] == "repeat" for item in ranges)
    # The adjacent pause and filler are deliberately merged into one safe cut.
    assert any(item["reason"] == "mixed" and item["start"] == pytest.approx(.45)
               and item["end"] == pytest.approx(1.2) for item in ranges)


def test_plan_rejects_removing_effectively_all_media():
    with pytest.raises(ValueError):
        normalize_edit_plan({"removed_ranges": [{"start": 0, "end": 9.9}]}, 10)


def test_ffmpeg_graph_concatenates_video_and_audio_before_normal_filters():
    graph = smart_edit_filter_complex(["scale=720:1280", "setpts=PTS-STARTPTS"], [
        {"start": 0, "end": 1}, {"start": 2, "end": 3.5},
    ])
    assert "[0:v]trim=start=0.000:end=1.000" in graph
    assert "[0:a]atrim=start=2.000:end=3.500" in graph
    assert "concat=n=2:v=1:a=1[vcat][acat]" in graph
    assert graph.endswith("[vcat]scale=720:1280,setpts=PTS-STARTPTS[vout]")


def test_reorder_plan_preserves_a_valid_segment_permutation():
    plan = normalize_edit_plan({
        "split_points": [2, 5],
        "segment_order": [2, 0, 1],
    }, 8)
    assert plan["version"] == 2
    assert plan["segment_order"] == [2, 0, 1]
    assert plan_reorders_segments(plan, 8) is True
    assert kept_ranges(plan, 8) == [
        {"start": 5.0, "end": 8},
        {"start": 0.0, "end": 5.0},
    ]


def test_invalid_reorder_falls_back_to_natural_order():
    plan = normalize_edit_plan({
        "split_points": [2, 5],
        "segment_order": [2, 2, 0],
    }, 8)
    assert plan["segment_order"] == [0, 1, 2]
    assert plan_reorders_segments(plan, 8) is False


def test_reorder_keeps_trim_and_delete_ranges_inside_their_source_segments():
    plan = normalize_edit_plan({
        "split_points": [2, 5],
        "segment_order": [2, 0, 1],
        "removed_ranges": [
            {"start": 5.0, "end": 5.5, "reason": "trim-l"},
            {"start": 2.5, "end": 3.0, "reason": "word"},
        ],
    }, 8)
    assert kept_ranges(plan, 8) == [
        {"start": 5.5, "end": 8},
        {"start": 0.0, "end": 2.5},
        {"start": 3.0, "end": 5.0},
    ]


def test_reordered_words_are_retimed_in_output_order():
    words = [
        {"start": .2, "end": .4, "text": "first"},
        {"start": 2.2, "end": 2.4, "text": "second"},
        {"start": 5.2, "end": 5.4, "text": "third"},
    ]
    plan = normalize_edit_plan({
        "split_points": [2, 5],
        "segment_order": [2, 0, 1],
    }, 8)
    edited = apply_plan_to_words(words, plan, 8)
    assert [item["text"] for item in edited] == ["third", "first", "second"]
    assert edited[0]["start"] == pytest.approx(.2)
    assert edited[1]["start"] == pytest.approx(3.2)
    assert edited[2]["start"] == pytest.approx(5.2)


def test_ffmpeg_graph_respects_reordered_kept_range_sequence():
    plan = normalize_edit_plan({
        "split_points": [2, 5],
        "segment_order": [2, 0, 1],
    }, 8)
    ranges = kept_ranges(plan, 8)
    graph = smart_edit_filter_complex(["scale=720:1280"], ranges)
    assert "[0:v]trim=start=5.000:end=8.000" in graph
    assert "[0:v]trim=start=0.000:end=5.000" in graph
    assert graph.index("trim=start=5.000:end=8.000") < graph.index("trim=start=0.000:end=5.000")

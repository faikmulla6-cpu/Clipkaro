from app.services.cartoon_timing import (
    approximate_word_boundaries,
    build_episode_lip_envelope,
    build_karaoke_caption_markup,
    group_caption_phrases,
    normalize_word_boundaries,
)


def test_edge_word_boundaries_convert_100ns_ticks_and_use_next_word_for_zero_duration():
    ticks = 10_000_000
    words = normalize_word_boundaries(
        [
            {"type": "WordBoundary", "offset": int(0.25 * ticks), "duration": 0, "text": "Ã›Å’Ã›Â"},
            {"type": "WordBoundary", "offset": int(0.40 * ticks), "duration": int(0.30 * ticks), "text": "Ã˜Â®Ã™Ë†Ã˜Â§Ã˜Â¨"},
            {"type": "WordBoundary", "offset": int(0.85 * ticks), "duration": int(0.20 * ticks), "text": "Ã›ÂÃ›â€™Ã›â€"},
        ],
        audio_duration=1.5,
        global_start=8.0,
        speaker_id="jannat",
        track="dialogue",
    )
    assert [word["text"] for word in words] == ["Ã›Å’Ã›Â", "Ã˜Â®Ã™Ë†Ã˜Â§Ã˜Â¨", "Ã›ÂÃ›â€™Ã›â€"]
    assert words[0]["start_seconds"] == 8.25
    assert words[0]["end_seconds"] == 8.4
    assert words[1]["start_seconds"] == 8.4
    assert words[1]["end_seconds"] == 8.7
    assert words[2]["speaker_id"] == "jannat"
    assert words[2]["source"] == "tts_word_boundary"


def test_word_boundaries_are_clamped_to_audio_duration_and_bad_events_are_ignored():
    words = normalize_word_boundaries(
        [
            {"offset": -1, "duration": 1_000_000, "text": "bad"},
            {"offset": 9_000_000, "duration": 50_000_000, "text": "last"},
            {"offset": "not-a-number", "duration": 1, "text": "invalid"},
        ],
        audio_duration=1.0,
    )
    assert len(words) == 1
    assert words[0]["start_seconds"] == 0.9
    assert words[0]["end_seconds"] == 1.0


def test_approximate_alignment_is_explicitly_marked_not_word_boundary():
    words = approximate_word_boundaries("Hello from ClipKaro", audio_duration=2.0, global_start=3.0)
    assert len(words) == 3
    assert words[0]["start_seconds"] == 3.0
    assert words[-1]["end_seconds"] == 5.0
    assert all(word["source"] == "estimated_from_text" for word in words)


def test_caption_groups_keep_word_timings_and_markup_is_rtl_safe_and_escaped():
    words = [
        {"text": "Ã›Å’Ã›Â", "start_seconds": 1.0, "end_seconds": 1.2},
        {"text": "Ã˜Â®Ã™Ë†Ã˜Â§Ã˜Â¨", "start_seconds": 1.2, "end_seconds": 1.6},
        {"text": "Ã›ÂÃ›â€™Ã›â€", "start_seconds": 1.6, "end_seconds": 2.0},
        {"text": "<script>", "start_seconds": 2.1, "end_seconds": 2.4},
    ]
    phrases = group_caption_phrases(words)
    assert len(phrases) == 1
    markup, timeline = build_karaoke_caption_markup(words, overlay_id="test", rtl=True)
    assert 'dir="rtl"' in markup
    assert "unicode-bidi:isolate;direction:rtl" in markup
    assert "unicode-bidi:plaintext" not in markup
    assert "&lt;script&gt;" in markup
    assert "<script>" not in markup
    assert "test-phrase-1-word-1" in timeline
    assert "color:\"#ffd76b\"" in timeline




def test_episode_lip_envelope_places_each_scene_voice_on_one_continuous_60hz_timeline():
    envelope = build_episode_lip_envelope(
        [
            {"lip_envelope": [0.2, 0.6, 0.1]},
            {"lip_envelope": [0.3, 0.8]},
        ],
        total_duration=4.0,
        slot_seconds=2.0,
        fps=10,
    )
    assert len(envelope) == 40
    assert envelope[3:6] == [0.2, 0.6, 0.1]
    assert envelope[23:25] == [0.3, 0.8]
    assert envelope[0:3] == [0.0, 0.0, 0.0]


def test_episode_lip_envelope_honors_scene_specific_dialogue_start_offsets():
    envelope = build_episode_lip_envelope(
        [
            {"lip_envelope": [0.2, 0.8], "speech_start_seconds": 6.2},
            {"lip_envelope": [0.3, 0.9], "speech_start_seconds": 1.05},
        ],
        total_duration=20,
        slot_seconds=10,
        fps=10,
    )
    assert len(envelope) == 200
    assert envelope[62:64] == [0.2, 0.8]
    assert envelope[110:112] == [0.3, 0.9]
    assert envelope[0:62] == [0.0] * 62

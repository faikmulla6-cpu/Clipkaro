from app.services.clip_finder import _clip_ready_segments, content_profile, find_clips, overlap_ratio


def test_finds_and_ranks_strong_moment():
    segments = [
        {"start": 0, "end": 10, "text": "Today we are discussing content."},
        {"start": 10, "end": 24, "text": "Most creators make this mistake and it stops their growth."},
        {"start": 24, "end": 43, "text": "The secret is to ask one question before publishing: does this solve a clear problem?"},
        {"start": 43, "end": 61, "text": "Follow these three steps and your audience will understand the value immediately."},
    ]
    clips = find_clips(segments, limit=3)
    assert clips
    assert clips[0]["score"] >= 80
    assert 20 <= clips[0]["end_time"] - clips[0]["start_time"] <= 90
    assert clips[0]["reason"]


def test_empty_transcript_returns_no_clips():
    assert find_clips([]) == []


def test_suggestions_do_not_substantially_overlap():
    segments = [
        {"start": i * 15, "end": (i + 1) * 15, "text": f"Step {i+1}: this is a useful business tip with a clear lesson."}
        for i in range(10)
    ]
    clips = find_clips(segments, limit=5)
    for i, clip in enumerate(clips):
        for other in clips[i + 1:]:
            assert overlap_ratio(clip, other) <= .5


def test_hinglish_hook_is_ranked_from_actual_opening_words():
    segments = [
        {"start": 0, "end": 12, "text": "Toh aaj hum normal baat karenge."},
        {"start": 12, "end": 28, "text": "Sabse badi galti kya hai pata hai? Log bina samjhe shuru karte hain."},
        {"start": 28, "end": 47, "text": "Asli tarika pehle problem samajhna hai, phir teen clear steps follow karo."},
        {"start": 47, "end": 64, "text": "Tab aapka kaam fast hoga aur result bhi sahi milega."},
    ]
    clips = find_clips(segments, limit=3)
    assert clips
    assert any(word in clips[0]["hook"].casefold() for word in ("galti", "kya", "pata", "asli"))
    assert clips[0]["score_breakdown"]["hook"] >= 70


def test_content_profile_changes_duration_strategy():
    tutorial = [{"start": 0, "end": 30, "text": "Pehle ye step karo phir dusra tarika follow karo."}]
    assert content_profile(tutorial)["content_type"] == "tutorial"


def test_overlap_ratio_uses_shorter_candidate_not_any_touch():
    a = {"start_time": 0, "end_time": 60}
    b = {"start_time": 45, "end_time": 90}
    assert round(overlap_ratio(a, b), 2) == .33


def test_long_api_segment_uses_native_word_aligned_windows_for_clips():
    words = [
        {"text": f"word{i}.", "display_text": f"word{i}.", "start": i * 5.0, "end": i * 5.0 + 1.0}
        for i in range(25)
    ]
    segment = {"start": 0.0, "end": 121.0, "text": "provider chunk", "display_text": "provider chunk", "words": words}
    windows = _clip_ready_segments([segment])
    assert len(windows) >= 2
    assert all(20 <= row["end"] - row["start"] <= 90 for row in windows)
    assert windows[0]["start"] == words[0]["start"]
    assert windows[0]["words"][0]["start"] == words[0]["start"]
    clips = find_clips([segment], limit=3)
    assert clips
    assert all(20 <= clip["end_time"] - clip["start_time"] <= 90 for clip in clips)


def test_long_segment_without_native_words_is_not_split():
    segment = {"start": 0.0, "end": 600.0, "text": "A long provider chunk without word timing."}
    assert _clip_ready_segments([segment]) == [segment]

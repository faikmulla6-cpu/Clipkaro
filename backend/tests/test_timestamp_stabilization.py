from app.services.timestamp_stabilization import stabilize_word_timestamps


def test_repairs_small_overlap_and_keeps_monotonic_words():
    rows = [{"start": 0, "end": 2, "text": "arre yaar", "words": [
        {"start": .1, "end": .7, "text": "arre"},
        {"start": .65, "end": 1.1, "text": "yaar"},
    ]}]
    output = stabilize_word_timestamps(rows)
    words = output[0]["words"]
    assert words[0]["end"] <= words[1]["start"]
    assert all(word["timing_stabilized"] for word in words)


def test_does_not_invent_missing_words():
    assert stabilize_word_timestamps([{"start": 0, "end": 2, "text": "hello", "words": []}]) == []

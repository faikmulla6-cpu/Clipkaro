from app.services.caption_layout import build_caption_cards, validate_cards


def words(text: str, step: float = .34):
    return [{"start": i * step, "end": i * step + .25, "text": token, "confidence": .9}
            for i, token in enumerate(text.split())]


def test_long_hinglish_is_wrapped_into_two_safe_lines():
    cards = build_caption_cards(words("mera moral hi khatam kar diya ab engineering ke upar baat karte hain"))
    assert cards
    assert all(len(card.lines) <= 2 for card in cards)
    assert all(len(line) <= 32 for card in cards for line in card.lines)
    assert not [e for e in validate_cards(cards) if "overflow" in e]


def test_pause_creates_phrase_boundary():
    stream = words("aap kya karte hain")
    stream += [{"start": 3.0, "end": 3.3, "text": "engineering"}]
    assert len(build_caption_cards(stream)) == 2


def test_invalid_word_timestamps_are_removed():
    stream = [{"start": 1, "end": 1, "text": "sir"}, {"start": 2, "end": 2.4, "text": "hello"}]
    cards = build_caption_cards(stream)
    assert [w["text"] for card in cards for w in card.words] == ["hello"]


def test_balanced_break_prefers_hinglish_conjunction():
    card = build_caption_cards(words("main samajh gaya lekin tum abhi bhi nahi samjhe"), max_words=12)[0]
    assert len(card.lines) == 2
    assert card.lines[1].startswith("lekin")

def test_india_pop_splits_projected_phrase_before_visual_overflow():
    stream = words("biological chronotype assessment", step=.34)
    cards = build_caption_cards(stream, max_chars=18, max_words=3, max_duration=2.2)
    assert len(cards) == 2
    assert [[word["text"] for word in card.words] for card in cards] == [
        ["biological", "chronotype"],
        ["assessment"],
    ]
    assert not [error for error in validate_cards(cards, max_chars=18) if "overflow" in error]


def test_pause_threshold_uses_real_speech_gap():
    stream = [
        {"start": 0.00, "end": 0.30, "text": "hello", "confidence": .9},
        {"start": 0.64, "end": 0.90, "text": "again", "confidence": .9},
    ]
    assert len(build_caption_cards(stream)) == 1

    stream[1]["start"] = 0.65
    stream[1]["end"] = 0.91
    cards = build_caption_cards(stream)
    assert len(cards) == 2
    assert cards[0].end == .30
    assert cards[1].start == .65


def test_speech_region_boundary_splits_even_when_timestamp_gap_is_short():
    stream = [
        {"start": 0.00, "end": 0.30, "text": "hello", "confidence": .9, "speech_region_id": 0},
        {"start": 0.36, "end": 0.62, "text": "again", "confidence": .9, "speech_region_id": 1},
    ]
    cards = build_caption_cards(stream)
    assert len(cards) == 2
    assert cards[0].end == .30
    assert cards[1].start == .36


def test_overlapping_caption_words_do_not_create_overlapping_cards():
    stream = [
        {"start": 0.00, "end": 1.20, "text": "FULLY.", "confidence": .9},
        {"start": 0.95, "end": 1.30, "text": "SOMETHING", "confidence": .9},
        {"start": 1.31, "end": 1.60, "text": "WHICH", "confidence": .9},
    ]
    cards = build_caption_cards(stream)
    assert len(cards) == 2
    assert cards[0].end == .95
    assert cards[1].start == .95
    assert cards[0].end <= cards[1].start

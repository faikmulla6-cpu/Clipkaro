from app.services.transcript_verification import transcript_agreement, verify_segments, word_error_rate


def test_independent_matching_hypotheses_pass():
    one = [{"text": "आज हम engineering के बारे में बात करेंगे"}]
    two = [{"text": "आज हम engineering के बारे में बात करेंगे।"}]
    assert transcript_agreement(one, two)["accepted"]


def test_phonetically_plausible_gibberish_disagreement_fails():
    one = [{"text": "mera moral hi khatam kar daake dekhunga"}]
    two = [{"text": "मेरी बात खत्म करके आपका नाम पूछूंगा"}]
    assert not transcript_agreement(one, two)["accepted"]


def test_one_bad_segment_is_not_hidden_by_global_transcript():
    primary = [{"start": 0, "end": 22, "text": "आज हम सही बात करेंगे"},
               {"start": 22, "end": 44, "text": "sir sir sir nonsense"}]
    secondary = [{"start": 0, "end": 22, "text": "आज हम सही बात करेंगे"},
                 {"start": 22, "end": 44, "text": "इंजीनियरिंग के बारे में बोलेंगे"}]
    result = verify_segments(primary, secondary)
    assert len(result["segments"]) == 1 and len(result["rejected"]) == 1


def test_word_error_rate_penalizes_insertions_and_deletions():
    assert word_error_rate("main bilkul theek hoon", "main theek hoon") == .25
    assert word_error_rate("main theek hoon", "main bilkul theek hoon") == 1 / 3


def test_repeated_filler_cannot_hide_behind_character_similarity():
    result = transcript_agreement([{"text": "sir sir sir sir engineering"}],
                                  [{"text": "engineering ke baare mein"}])
    assert not result["accepted"] and result["word_error_rate"] >= .8

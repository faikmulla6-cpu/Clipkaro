import inspect

from app.services import roman_hinglish_hybrid_v3 as hybrid


def generated(base, sarvam, shunya, words=None):
    return hybrid.generate("case", base, sarvam, shunya, elevenlabs_words=words)


def test_all_agree_keeps_base_without_corrections():
    result = generated("aaj meeting cancel", "aaj meeting cancel", "aaj meeting cancel")
    assert result["hybrid_transcript"] == "aaj meeting cancel" and not result["corrections"]


def test_two_secondaries_can_correct_short_substitution():
    result = generated("aaj meeting cancer ho gayi", "aaj meeting cancel ho gayi", "aaj meeting cancel ho gayi")
    assert result["hybrid_transcript"] == "aaj meeting cancel ho gayi"
    assert result["counts"]["substitutions"] == 1


def test_one_secondary_disagreement_and_missing_sarvam_keep_base():
    assert generated("aaj cancer", "aaj cancer", "aaj cancel")["hybrid_transcript"] == "aaj cancer"
    assert generated("aaj cancer", None, "aaj cancel")["hybrid_transcript"] == "aaj cancer"


def test_safe_insert_delete_and_large_or_ambiguous_spans_are_fail_closed():
    assert generated("aaj meeting", "aaj client meeting", "aaj client meeting")["hybrid_transcript"] == "aaj client meeting"
    assert generated("aaj extra meeting", "aaj meeting", "aaj meeting")["hybrid_transcript"] == "aaj meeting"
    assert generated("one two three four", "alpha beta gamma delta", "alpha beta gamma delta")["hybrid_transcript"] == "one two three four"


def test_inherited_and_derived_timestamp_labels_are_not_native():
    words = [{"start": 0, "end": .2}, {"start": .2, "end": .6}, {"start": .6, "end": 1}]
    replaced = generated("aaj cancer now", "aaj cancel now", "aaj cancel now", words)
    assert replaced["tokens"][1]["timestamp_source"] == "inherited_span_timestamp"
    inserted = generated("aaj now", "aaj client now", "aaj client now", words[:2])
    assert any(token["timestamp_source"] == "derived_gap" for token in inserted["tokens"])


def test_generation_module_has_no_reference_or_scoring_dependency():
    source = inspect.getsource(hybrid)
    assert "asr_policy_v2" not in source and "error_rate" not in source and "stress_corpus" not in source

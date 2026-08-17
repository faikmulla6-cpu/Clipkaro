from app.services.roman_hinglish_policy_v3 import error_rate_v3, normalize_v3, policy_sha256


def test_v3_romanizes_generic_hindi_and_preserves_latin_english():
    assert normalize_v3("आज") == "aaj"
    assert normalize_v3("मैं") == "main"
    assert normalize_v3("नहीं") == "nahi"
    assert normalize_v3("हो गया") == "ho gaya"
    assert normalize_v3("meeting cancel client timing") == "meeting cancel client timing"


def test_v3_maps_only_documented_mechanical_loanword_forms():
    assert normalize_v3("मीटिंग") == "meeting"
    assert normalize_v3("क्लाइंट") == "client"
    assert normalize_v3("टाइमिंग") == "timing"
    assert error_rate_v3("meeting client timing", "मीटिंग क्लाइंट टाइमिंग") == 0


def test_v3_preserves_real_lexical_distinctions_and_never_fuzzy_matches():
    assert normalize_v3("कल") != normalize_v3("काल")
    assert normalize_v3("कर") != normalize_v3("घर")
    assert error_rate_v3("kal", "kaal") == 1


def test_v3_is_symmetric_and_deterministic_for_punctuation_and_annotations():
    reference = "<noise> आज, meeting! [music]"
    hypothesis = "aaj meeting"
    assert error_rate_v3(reference, hypothesis) == 0
    assert policy_sha256() == policy_sha256()

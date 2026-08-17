from app.services.roman_hindi import romanize_hindi, add_roman_display_text


def test_natural_roman_hindi_examples():
    assert romanize_hindi("मैं कैसे हूँ") == "main kaise hoon"
    assert romanize_hindi("अरे यार हाँ सही में") == "arre yaar haan sahi mein"
    assert romanize_hindi("क्या करूँ") == "kya karoon"


def test_code_switched_english_is_preserved():
    result = romanize_hindi("आज engineering के ऊपर बात करेंगे")
    assert "engineering" in result
    assert not any("\u0900" <= ch <= "\u097f" for ch in result)


def test_source_text_and_alignment_are_preserved():
    rows = [{"text": "मैं ठीक हूँ", "words": [{"text": "मैं", "start": 0, "end": .3}]}]
    output = add_roman_display_text(rows, True)
    assert output[0]["source_text"] == "मैं ठीक हूँ"
    assert output[0]["words"][0]["start"] == 0
    assert output[0]["words"][0]["display_text"] == "main"

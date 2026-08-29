from app.schemas.api import ExportRequest
from app.services.india_quality import (
    caption_segments_for_export,
    effective_caption_position,
    language_profile,
    transcript_review_summary,
)


def _segment(text: str, *, confidence: float = .92, start: float = 0, language: str = "hinglish") -> dict:
    tokens = text.split()
    words = [
        {"start": start + index * .35, "end": start + index * .35 + .28, "text": token, "confidence": confidence}
        for index, token in enumerate(tokens)
    ]
    return {
        "start": start,
        "end": start + max(1.0, len(tokens) * .35),
        "text": text,
        "language": language,
        "words": words,
    }


def test_export_request_keeps_old_payload_defaults():
    request = ExportRequest()
    assert request.india_quality_mode is False
    assert request.caption_language_style == "auto"
    assert request.preserve_source_captions is False


def test_hinglish_input_is_identified_without_perfect_classifier():
    profile = language_profile([
        _segment("This engineering ka scene hi alag hai"),
        _segment("Placement ke time sab serious ho jaate hain", start=3),
    ], "auto")
    assert profile["india_quality_suitable"] is True
    assert profile["likely_language_style"] == "hinglish"


def test_roman_caption_mode_travels_to_caption_segments():
    prepared = caption_segments_for_export(
        [_segment("भाई mujhe samajh nahi aaya")],
        "hinglish",
        india_quality_mode=True,
        caption_language_style="roman_hinglish",
    )
    texts = [word.get("display_text") or word["text"] for word in prepared[0]["words"]]
    assert not any("भाई" in text for text in texts)
    assert any("bhai" in text.casefold() for text in texts)


def test_mode_off_leaves_caption_segments_unchanged():
    original = [_segment("भाई mujhe samajh nahi aaya")]
    prepared = caption_segments_for_export(original, "hinglish")
    assert prepared[0]["words"][0]["text"] == "भाई"
    assert "display_text" not in prepared[0]["words"][0]


def test_source_caption_preserve_moves_generated_captions_to_safe_zone_only_in_mode():
    assert effective_caption_position(True, True, "bottom") == "above"
    assert effective_caption_position(False, True, "bottom") == "bottom"
    assert effective_caption_position(True, True, "center") == "center"


def test_low_confidence_review_warning_is_meaningful_not_spammy():
    confident = transcript_review_summary([_segment("Placement ke time sab serious ho jaate hain")], "hinglish")
    uncertain = transcript_review_summary([_segment("foo foo foo foo", confidence=.31)], "hinglish")
    assert confident["review_suggested"] is False
    assert uncertain["review_suggested"] is True
    assert "low_word_confidence" in uncertain["review_reasons"]

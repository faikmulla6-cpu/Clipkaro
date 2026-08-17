from app.services.transcription import needs_hindi_retry


def test_india_auto_mode_retries_urdu_as_hindi():
    assert needs_hindi_retry("ur", .99, "auto", "india")


def test_uncertain_english_gets_hindi_comparison():
    assert needs_hindi_retry("en", .55, "auto", "india")
    assert not needs_hindi_retry("en", .92, "auto", "india")


def test_explicit_language_is_never_overridden():
    assert not needs_hindi_retry("ur", .99, "en", "india")
    assert not needs_hindi_retry("ur", .99, "auto", "global")

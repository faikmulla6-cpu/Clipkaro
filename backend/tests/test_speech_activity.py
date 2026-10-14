from app.services.speech_activity import _regions_from_voicing


def test_sustained_pause_creates_separate_speech_regions():
    flags = [False] * 5 + [True] * 10 + [False] * 10 + [True] * 10 + [False] * 10
    regions = _regions_from_voicing(flags)
    assert len(regions) == 2
    assert regions[0]["end"] < regions[1]["start"]
    assert regions[0]["end"] <= .40
    assert regions[1]["start"] >= .44


def test_brief_unvoiced_run_does_not_fragment_continuous_speech():
    flags = [False] * 5 + [True] * 10 + [False] * 4 + [True] * 10 + [False] * 10
    regions = _regions_from_voicing(flags)
    assert len(regions) == 1

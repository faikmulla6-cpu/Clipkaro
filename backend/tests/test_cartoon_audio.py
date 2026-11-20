from app.services.cartoon_audio import rms_envelope_from_samples


def test_rms_envelope_is_silent_for_zero_audio():
    envelope = rms_envelope_from_samples([0.0] * 4800, sample_rate=48_000, fps=60)
    assert len(envelope) == 6
    assert all(value == 0.0 for value in envelope)


def test_rms_envelope_tracks_voice_energy_at_60fps_and_stays_bounded():
    quiet = [0.001] * 800
    loud = [0.5] * 800
    samples = quiet + loud + loud + quiet
    envelope = rms_envelope_from_samples(samples, sample_rate=48_000, fps=60)
    assert len(envelope) == 4
    assert all(0.0 <= value <= 1.0 for value in envelope)
    assert envelope[1] > envelope[0]
    assert envelope[2] >= envelope[1]
    assert envelope[3] < envelope[2]

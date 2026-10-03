from app.services.pipeline_provenance import PIPELINE_FINGERPRINT, PIPELINE_VERSION, stamp_segments, transcript_state


def test_missing_and_legacy_transcripts_are_not_export_safe():
    assert transcript_state([])["reason"] == "missing_transcript"
    state = transcript_state([{"text": "legacy", "start": 0, "end": 1}])
    assert state == {"current": False, "export_safe": False, "reason": "stale_pipeline"}


def test_manual_transcript_is_safe_after_current_pipeline_stamp():
    segments = stamp_segments([{"text": "main theek hoon", "start": 0, "end": 1}], "manual")
    assert transcript_state(segments) == {"current": True, "export_safe": True, "reason": "verified"}


def test_asr_transcript_requires_consensus_and_stable_word_alignment():
    base = {
        "text": "main theek hoon", "start": 0, "end": 1, "transcript_origin": "asr",
        "pipeline_version": PIPELINE_VERSION, "pipeline_fingerprint": PIPELINE_FINGERPRINT,
    }
    assert transcript_state([base])["reason"] == "missing_speech_activity"
    base = {
        **base,
        "speech_activity_version": "webrtc-vad-20ms-v1",
        "speech_regions": [{"start": 0.0, "end": 1.0}],
    }
    assert transcript_state([{**base, "agreement_score": .3}])["reason"] == "missing_consensus"
    assert transcript_state([{**base, "agreement_score": .9}])["reason"] == "missing_alignment"
    verified = {**base, "agreement_score": .9, "alignment_status": "native_stabilized",
                "words": [{"text": "main", "start": 0, "end": .3}]}
    assert transcript_state([verified])["export_safe"] is True
    assert transcript_state([verified], require_forced_alignment=True)["reason"] == "missing_alignment"
    forced = {**verified, "alignment_status": "forced_aligned", "alignment_backend": "whisperx"}
    assert transcript_state([forced], require_forced_alignment=True)["export_safe"] is True

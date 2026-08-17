from app.services.asr_quality import assess_transcript, segment_quality


def test_rejects_repeated_hallucination():
    segment = {"start": 0, "end": 30, "text": "Sir " * 110,
               "words": [{"start": 1, "end": 1, "text": "Sir", "confidence": .9}] * 20,
               "compression_ratio": 3.2}
    quality = segment_quality(segment, "hi")
    assert not quality["accepted"]
    assert "dominant_repetition" in quality["flags"]
    assert "collapsed_word_timestamps" in quality["flags"]


def test_rejects_wrong_script_for_hindi():
    quality = segment_quality({"start": 0, "end": 10, "text": "یہ غلط اردو عبارت ہے"}, "hi")
    assert not quality["accepted"]
    assert "foreign_script" in quality["flags"]


def test_accepts_timed_hindi_dialogue():
    text = "आज हम इंजीनियरिंग के बारे में एक जरूरी बात समझेंगे और सही उदाहरण देखेंगे"
    words = [{"start": i * .5, "end": i * .5 + .35, "text": w, "confidence": .91}
             for i, w in enumerate(text.split())]
    segment = {"start": 0, "end": 22, "text": text, "words": words}
    assert segment_quality(segment, "hi")["accepted"]
    assert assess_transcript([segment], "hi")["accepted"]

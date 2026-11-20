from app.services.cartoon_renderer import build_cartoon_project


def test_cartoon_renderer_uses_rtl_word_timed_captions_and_audio_energy_for_mouth():
    dialogue = "\u06cc\u06c1 \u062e\u0648\u0627\u0628 \u0627\u062a\u0646\u0627 \u062d\u0642\u06cc\u0642\u06cc \u06a9\u06cc\u0648\u06ba \u0644\u06af \u0631\u06c1\u0627 \u062a\u06be\u0627\u061f"
    project = {
        "duration_seconds": 15,
        "aspect_ratio": "9:16",
        "style": "2d-cartoon",
        "language": "ur",
    }
    storyboard = {
        "title": "Jannat",
        "characters": [{
            "id": "jannat",
            "name": "Jannat",
            "role": "main character",
            "species": "human",
            "voice_type": "female",
            "appearance": {
                "skin_color": "#ca9a85",
                "hair_color": "#121c29",
                "shirt_color": "#306b73",
                "pants_color": "#306b73",
                "shoe_color": "#17202b",
                "hair_style": "long",
            },
        }],
        "scenes": [{
            "id": "scene-1",
            "scene_title": "\u062e\u0648\u0627\u0628 \u0633\u06d2 \u062c\u0627\u06af\u0646\u0627",
            "environment": "home",
            "action": "Jannat wakes up in her bedroom",
            "expression": "scared",
            "motion": "look",
            "camera_move": "push-in",
            "character_ids": ["jannat"],
            "speaker_id": "jannat",
            "dialogue": dialogue,
        }],
    }
    words = [
        {"text": "\u06cc\u06c1", "start_seconds": 1.2, "end_seconds": 1.4, "source": "tts_word_boundary"},
        {"text": "\u062e\u0648\u0627\u0628", "start_seconds": 1.4, "end_seconds": 1.8, "source": "tts_word_boundary"},
        {"text": "\u0627\u062a\u0646\u0627", "start_seconds": 1.8, "end_seconds": 2.2, "source": "tts_word_boundary"},
    ]
    files = build_cartoon_project(
        project,
        storyboard,
        [{
            "scene_id": "scene-1",
            "filename": "scene-1.mp3",
            "duration": 2.4,
            "words": words,
            "lip_envelope": [0.0, 0.2, 0.8, 0.4, 0.0],
            "animation_filename": "scene-1.mp4",
        }],
    )
    html = files["compositions/scene-1.html"]
    assert '<html lang="ur" dir="rtl"' in files["index.html"]
    assert 'dir="rtl"' in html
    assert "scene-1-phrase-1" in html
    assert '<video id="scene-1-animation"' in html
    assert 'src="assets/animation/scene-1.mp4"' in html
    assert "\u062e\u0648\u0627\u0628" in html
    assert 'data-start="1.2000"' in html
    assert 'color:"#ffd76b"' in html
    assert 'data-layout-ignore' in html
    assert 'id="scene-1-dialogue"' not in html


def test_jannat_hyperframes_mix_keeps_narration_music_and_foley_as_separate_tracks():
    project = {
        "duration_seconds": 30,
        "aspect_ratio": "16:9",
        "style": "cinematic-jannat",
        "language": "ur",
        "narration_words": [
            {
                "text": "Ø¢Ø¯Ú¾ÛŒ",
                "start_seconds": 0.4,
                "end_seconds": 0.7,
                "speaker_id": "narrator",
                "track": "narration",
            }
        ],
        "audio_tracks": [
            {
                "track": "narration",
                "filename": "narration.mp3",
                "start_seconds": 0.4,
                "duration_seconds": 4.4,
                "volume": 1.0,
                "fade_in_seconds": 0.05,
                "fade_out_seconds": 0.15,
            },
            {
                "track": "music",
                "filename": "score.wav",
                "start_seconds": 0,
                "duration_seconds": 30,
                "volume": 0.75,
            },
            {
                "track": "foley",
                "filename": "foley.wav",
                "start_seconds": 0,
                "duration_seconds": 30,
                "volume": 1.0,
            },
        ],
    }
    storyboard = {
        "title": "Jannat",
        "characters": [{"id": "jannat", "name": "Jannat", "species": "human", "appearance": {}}],
        "scenes": [{
            "id": "scene-1",
            "environment": "home",
            "character_ids": ["jannat"],
            "speaker_id": "jannat",
            "dialogue": "ÛŒÛ Ø®ÙˆØ§Ø¨ Ø§ØªÙ†Ø§ Ø­Ù‚ÛŒÙ‚ÛŒ Ú©ÛŒÙˆÚº Ù„Ú¯ Ø±ÛØ§ ØªÚ¾Ø§ØŸ",
        }],
    }
    files = build_cartoon_project(
        project,
        storyboard,
        [{
            "scene_id": "scene-1",
            "filename": "scene-1.mp3",
            "duration": 3.0,
            "words": [{"text": "Ø®ÙˆØ§Ø¨", "start_seconds": 6.2, "end_seconds": 6.6}],
            "speech_start_seconds": 6.2,
        }],
    )
    root = files["index.html"]
    scene = files["compositions/scene-1.html"]
    assert 'src="assets/audio/narration.mp3"' in root
    assert 'src="assets/audio/score.wav"' in root
    assert 'src="assets/audio/foley.wav"' in root
    assert 'data-track-index="10"' in root
    assert 'data-track-index="40"' in root
    assert 'data-track-index="50"' in root
    assert 'data-fade-in="0.040"' in root
    assert 'data-fade-out="0.120"' in root
    assert 'data-track-kind="audio"' in root
    assert 'data-start="0.4000"' in scene
    assert 'data-start="6.2000"' in scene
    assert "Ø¢Ø¯Ú¾ÛŒ" in scene
    assert "Ø®ÙˆØ§Ø¨" in scene

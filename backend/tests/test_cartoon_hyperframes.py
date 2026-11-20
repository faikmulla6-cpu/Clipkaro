from app.services.cartoon_hyperframes import build_final_hyperframes_project


def test_final_hyperframes_project_has_muted_remotion_video_separate_audio_and_rtl_captions():
    files = build_final_hyperframes_project(
        project_id="test-project",
        title="جنت کی کہانی",
        duration_seconds=15,
        aspect_ratio="16:9",
        animation_filename="animation.mp4",
        language="ur",
        audio_tracks=[
            {"filename": "narration.mp3", "start_seconds": 0.2, "duration_seconds": 2.5, "track": "narration", "volume": 1},
            {"filename": "dialogue.mp3", "start_seconds": 5.0, "duration_seconds": 3.0, "track": "dialogue", "volume": 1},
            {"filename": "score.wav", "start_seconds": 0, "duration_seconds": 15, "track": "music", "volume": 0.35},
            {"filename": "foley.wav", "start_seconds": 0, "duration_seconds": 15, "track": "foley", "volume": 0.5},
        ],
        caption_words=[
            {"text": "یہ", "start_seconds": 5.2, "end_seconds": 5.5},
            {"text": "خواب", "start_seconds": 5.5, "end_seconds": 6.0},
            {"text": "ہے۔", "start_seconds": 6.0, "end_seconds": 6.4},
        ],
    )
    html = files["index.html"]
    assert '<html lang="ur" dir="rtl">' in html
    assert 'src="assets/animation.mp4" muted playsinline' in html
    assert 'src="assets/audio/narration.mp3"' in html
    assert 'src="assets/audio/dialogue.mp3"' in html
    assert 'src="assets/audio/score.wav"' in html
    assert 'src="assets/audio/foley.wav"' in html
    assert 'data-start="5.2000"' in html
    assert "یہ خواب ہے۔" in html
    assert 'data-track-index="30"' in html
    assert "window.__timelines[\"main\"] = tl;" in html
    assert "hyperframes.json" in files
    assert "meta.json" in files


def test_final_hyperframes_project_rejects_unsafe_asset_paths_and_clamps_tracks():
    files = build_final_hyperframes_project(
        project_id="test",
        title="Safe",
        duration_seconds=10,
        aspect_ratio="9:16",
        animation_filename="../secret.mp4",
        language="en",
        audio_tracks=[
            {"filename": "../../secret.mp3", "start_seconds": 0, "duration_seconds": 10, "track": "dialogue"},
            {"filename": "safe.mp3", "start_seconds": 9, "duration_seconds": 5, "track": "dialogue"},
        ],
        caption_words=[],
    )
    html = files["index.html"]
    assert 'src="assets/animation.mp4"' in html
    assert "secret.mp3" not in html
    assert 'data-duration="1.0000"' in html

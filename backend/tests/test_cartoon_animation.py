from pathlib import Path

from app.services.cartoon_renderer import build_cartoon_project


def _storyboard():
    dialogue = "\u06cc\u06c1 \u062e\u0648\u0627\u0628 \u0627\u062a\u0646\u0627 \u062d\u0642\u06cc\u0642\u06cc \u06a9\u06cc\u0648\u06ba \u0644\u06af \u0631\u06c1\u0627 \u062a\u06be\u0627\u061f"
    return dialogue, {
        "title": "Jannat",
        "characters": [{
            "id": "jannat", "name": "Jannat", "species": "human", "voice_type": "female",
            "appearance": {
                "skin_color": "#ca9a85", "hair_color": "#121c29", "shirt_color": "#306b73",
                "pants_color": "#306b73", "shoe_color": "#17202b", "hair_style": "long",
            },
        }],
        "scenes": [{
            "id": "scene-1", "scene_title": "\u062e\u0648\u0627\u0628 \u0633\u06d2 \u062c\u0627\u06af\u0646\u0627",
            "environment": "home", "action": "Jannat wakes up after a strange dream",
            "expression": "scared", "motion": "look", "camera_move": "push-in",
            "character_ids": ["jannat"], "speaker_id": "jannat", "dialogue": dialogue,
        }],
    }


def test_imported_video_is_the_scene_plate_and_hyperframes_keeps_audio_and_rtl_captions_separate():
    dialogue, storyboard = _storyboard()
    files = build_cartoon_project(
        {"duration_seconds": 5, "aspect_ratio": "9:16", "style": "2d-cartoon", "language": "ur"},
        storyboard,
        [{
            "scene_id": "scene-1", "filename": "scene-1.mp3", "duration": 3.2,
            "animation_filename": "scene-1.mp4",
            "words": [
                {"text": "\u06cc\u06c1", "start_seconds": 0.8, "end_seconds": 1.0},
                {"text": "\u062e\u0648\u0627\u0628", "start_seconds": 1.0, "end_seconds": 1.4},
            ],
        }],
    )
    scene_html = files["compositions/scene-1.html"]
    root_html = files["index.html"]
    assert 'src="assets/animation/scene-1.mp4"' in scene_html
    assert 'data-track-kind="video"' in scene_html
    assert "muted playsinline" in scene_html
    assert 'dir="rtl"' in scene_html
    assert "scene-1-phrase-1" in scene_html
    assert 'color:"#ffd76b"' in scene_html
    assert "bottom:30%" in scene_html
    assert 'class="scene-heading"' not in scene_html
    assert 'src="assets/audio/scene-1.mp3"' in root_html
    assert 'data-track-index="20"' in root_html
    assert "Jannat wakes up after a strange dream" not in scene_html
    assert dialogue.split()[0] in scene_html


def test_native_animation_uses_the_worker_bundle_and_preserves_the_caption_layer():
    _, storyboard = _storyboard()
    files = build_cartoon_project(
        {"duration_seconds": 30, "aspect_ratio": "16:9", "style": "cinematic-jannat",
         "language": "ur", "native_animation": True, "episode_lip_envelope": [0, 0.5]},
        storyboard,
        [{"scene_id": "scene-1", "duration": 2.1,
          "words": [{"text": "Hello", "start_seconds": 6.2, "end_seconds": 7.1}]}],
    )
    root = files["index.html"]
    assert 'src="assets/animation.js"' in root
    assert 'id="cartoon-animation"' in root
    assert '"kind": "jannat", "envelope": [0, 0.5]' in root
    scene = files["compositions/scene-1.html"]
    assert "background:transparent" in scene
    assert 'dir="rtl"' in scene
    assert "Hello" in scene

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
BACKEND = ENGINE.parent
sys.path.insert(0, str(BACKEND))
from app.services.cartoon_renderer import build_cartoon_project  # noqa: E402

PROJECT = ENGINE / "smoke-project"
AUDIO = PROJECT / "assets" / "audio"
AUDIO.mkdir(parents=True, exist_ok=True)

characters = [
    {
        "id": "milo-fox",
        "name": "Milo",
        "role": "curious fox",
        "species": "fox",
        "voice_id": "Puck",
        "appearance": {
            "skin_color": "#E77A32",
            "hair_color": "#8D3D20",
            "shirt_color": "#E87552",
            "pants_color": "#405D86",
            "shoe_color": "#3A3441",
            "hair_style": "spiky",
        },
    },
    {
        "id": "wise-owl",
        "name": "Ollie",
        "role": "wise owl",
        "species": "owl",
        "voice_id": "Charon",
        "appearance": {
            "skin_color": "#A66B43",
            "hair_color": "#4B352C",
            "shirt_color": "#4F9B70",
            "pants_color": "#405D86",
            "shoe_color": "#3A3441",
            "hair_style": "curly",
        },
    },
]
storyboard = {
    "title": "The Glowing Map",
    "summary": "Milo finds a glowing map and asks Ollie the owl for help.",
    "characters": characters,
    "scenes": [
        {
            "id": "scene-one",
            "scene_title": "A Strange Discovery",
            "environment": "forest",
            "action": "Milo notices a glowing map beneath an old tree.",
            "dialogue": "Ollie, look! This map is shining!",
            "speaker_id": "milo-fox",
            "character_ids": ["milo-fox", "wise-owl"],
            "expression": "curious",
            "motion": "look",
            "camera_move": "push-in",
        },
        {
            "id": "scene-two",
            "scene_title": "The First Clue",
            "environment": "forest",
            "action": "Ollie points toward the stars as Milo listens.",
            "dialogue": "Follow the stars, Milo. Your adventure starts tonight!",
            "speaker_id": "wise-owl",
            "character_ids": ["milo-fox", "wise-owl"],
            "expression": "happy",
            "motion": "wave",
            "camera_move": "pan-right",
        },
    ],
}

audio_assets = []
for index, scene in enumerate(storyboard["scenes"], start=1):
    filename = f"scene-{index}.mp3"
    audio_path = AUDIO / filename
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000",
            "-t", "3.0", "-codec:a", "libmp3lame", "-b:a", "64k", str(audio_path),
        ],
        check=True,
    )
    audio_assets.append({"scene_id": scene["id"], "filename": filename, "duration": 3.0})

gsap = ENGINE / "node_modules" / "gsap" / "dist" / "gsap.min.js"
if not gsap.is_file():
    raise SystemExit("GSAP dependency is missing.")
shutil.copy2(gsap, PROJECT / "assets" / "gsap.min.js")

project = {"duration_seconds": 15, "aspect_ratio": "9:16", "style": "2d-cartoon"}
render_files = build_cartoon_project(project, storyboard, audio_assets)
for relative_path, content in render_files.items():
    target_path = PROJECT / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
(PROJECT / "hyperframes.json").write_text(
    json.dumps(
        {
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
            "media": {"autoProxy": True},
        },
        indent=2,
    ),
    encoding="utf-8",
)
(PROJECT / "meta.json").write_text(
    json.dumps({"id": "smoke-cartoon", "name": "Cartoon Studio Smoke Test"}, indent=2),
    encoding="utf-8",
)
print(PROJECT)

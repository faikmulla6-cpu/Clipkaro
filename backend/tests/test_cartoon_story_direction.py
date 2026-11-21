from app.services.cartoon_story import normalize_director_story
from app.services.cartoon_story_direction import direct_story
from story_v3_fixtures import action, actor, scene


def test_direction_uses_requested_dialogue_beat_and_carries_colored_prop():
    pip, dog = "pip", "dog"
    table = {"id": "table", "type": "table", "x": .65}
    box = {"id": "box", "type": "box", "x": .65, "support_id": "table"}
    ball = {"id": "red_ball", "type": "ball", "x": .65, "support_id": "table"}
    line = {"speaker_id": pip, "text": "I've always wanted one.", "start": 6.5}
    raw = {
        "characters": [{**actor(pip, "Pip"), "species": "robot"}, {**actor(dog, "Dog"), "species": "dog"}],
        "scenes": [
            scene(10, "workshop", [pip], [action(pip, "idle", 0, 2), action(pip, "look", 8, 9, target_id="box")],
                  props=[table, box], speech=[dict(line)]),
            scene(10, "workshop", [pip], [action(pip, "open_box", 2, 4, target_id="box"),
                                           action(pip, "pick_up", 6, 8, target_id="red_ball")],
                  props=[table, box, ball], speech=[dict(line)]),
            scene(10, "garden", [pip, dog], [action(pip, "walk", 0, 2), action(pip, "put_down", 2, 4, target_id="red_ball"),
                                            action(dog, "jump", 8, 10)],
                  props=[{"id": "red_ball", "type": "ball", "x": .35}],
                  camera=[{"time": 0, "shot": "wide", "focus_id": pip}, {"time": 8, "shot": "wide", "focus_id": dog}]),
        ],
    }
    prompt = """0–10 seconds. Pip finds a box.
    10–20 seconds. He sees a bright red ball. He picks it up. “I’ve always wanted one.”
    20–30 seconds. The dog wags its tail and hops. Use a soft creak when the box opens."""
    story = direct_story(normalize_director_story(raw, duration=30), prompt)
    first, reveal, ending = story["scenes"]
    assert first["speech"] == []
    assert [(s["text"], s["start"]) for s in reveal["speech"]] == [("I’ve always wanted one.", 8.0)]
    assert first["actions"][0]["type"] == "head"
    assert first["camera"][0]["focus_id"] == "box"
    assert reveal["sounds"] == [{"type": "door_creak", "at": 2.0}]
    assert reveal["props"][2]["color"] == ending["props"][0]["color"] == "#DC414F"
    assert ending["props"][0]["holder_id"] == "pip"
    assert ending["actions"][-1]["end"] == 8.85
    assert ending["camera"][-1]["shot"] == "medium"
    assert any(a["type"] == "wag" and a["character_id"] == dog for a in ending["actions"])
    rebuilt = normalize_director_story(story, duration=30)
    assert rebuilt["scenes"][2]["props"][0]["holder_id"] == "pip"


def test_authored_repetition_and_unscripted_dialogue_are_kept():
    raw = {"characters": [actor("lead", "Lead")], "scenes": [
        scene(15, "home", ["lead"], [action("lead", "look", 0, 2)], speech=[
            {"speaker_id": "lead", "text": "Are you there?", "start": 1},
            {"speaker_id": "lead", "text": "Are you there?", "start": 4},
            {"speaker_id": "lead", "text": "Come in!", "start": 8},
        ]),
    ]}
    story = normalize_director_story(raw, duration=15)
    result = direct_story(story, 'She calls, “Are you there?” After a pause, “Are you there?”')
    assert [s["text"] for s in result["scenes"][0]["speech"]] == [
        "Are you there?", "Are you there?", "Come in!",
    ]

"""Validated, data-only director contract. No model-authored code reaches a browser."""
from __future__ import annotations

import copy
import math
import re
from typing import Any

STORY_VERSION = 3
ENVIRONMENTS = {"bedroom", "home", "forest", "garden", "city", "school", "beach", "space", "castle", "mountain", "desert", "workshop"}
ACTIONS = {"idle", "sleep", "wake", "walk", "run", "sit", "stand", "turn", "look", "head", "blink", "wave", "wag", "point", "reach", "pick_up", "put_down", "open_door", "close_door", "open_box", "react", "jump", "speak"}
OPENABLE_ACTIONS = {"open_door": "door", "close_door": "door", "open_box": "box"}
BOX_CONTENTS = {"letter", "book", "pendant", "ball", "cup"}
EXPRESSIONS = {"neutral", "happy", "sad", "scared", "surprised", "angry", "curious"}
PROPS = {"door", "bed", "table", "chair", "letter", "book", "pendant", "ball", "box", "lamp", "cup", "tree"}
PROP_SUPPORTS = {"table", "bed", "chair"}
MAX_SCENE_PROPS = 12
PROP_COLORS = {
    "red": "#DC414F", "blue": "#3F7DCF", "green": "#4B9660", "yellow": "#EDC440",
    "orange": "#E78842", "purple": "#9159B1", "pink": "#DC739F", "white": "#FAF4E8",
    "black": "#263142", "brown": "#9B6748", "gold": "#D5AC54", "silver": "#C1CAD3",
}
SOUNDS = {"footstep", "rustle", "door_click", "door_creak", "gasp", "knock", "chime", "pickup"}
RATIOS = {"9:16": (1080, 1920, "portrait"), "16:9": (1920, 1080, "landscape"), "1:1": (1080, 1080, "square"), "4:5": (1080, 1350, "portrait")}


class StoryValidationError(ValueError):
    pass


class DialogueSpeakerError(StoryValidationError):
    pass


def resolve_cartoon_language(language: str, prompt: str) -> str:
    """Honor explicit Roman Hindi or Hinglish when the form defaults to Hindi."""
    if language in {"hi", "auto"} and re.search(
        r"\broman(?:[- ]script)?[- ]+(?:hindi|hinglish)\b", prompt, re.IGNORECASE
    ):
        return "hinglish"
    return language


def director_response_schema() -> dict:
    """Constrain GLM's response shape before checking cross-field story rules."""
    string = {"type": "string"}
    numeric = {"type": "number"}
    optional_id = {"type": ["string", "null"]}

    def obj(**properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

    def array(items):
        return {"type": "array", "items": items}

    def choices(values):
        return {"type": "string", "enum": sorted(values)}

    position = {"x": numeric, "y": numeric}
    appearance = obj(
        skin_color=string, hair_color=string, shirt_color=string, pants_color=string,
        shoe_color=string, eye_color=string,
        hair_style=choices(["short", "long", "curly", "spiky", "bald"]),
        clothing=choices(["shirt", "kameez", "dress", "jacket"]),
        face_shape=choices(["oval", "round", "angular"]), body_scale=numeric,
    )
    actor = obj(character_id=string, **position, pose=choices(["stand", "sit", "sleep"]), facing=numeric, scale=numeric)
    prop = obj(id=string, type=choices(PROPS), **position, state=choices(["open", "closed"]), color=string,
               support_id=optional_id, reveal_from_id=optional_id)
    action = obj(
        character_id=string, type=choices(ACTIONS), start=numeric, end=numeric,
        to={"anyOf": [obj(**position), {"type": "null"}]}, target_id=optional_id,
        expression=choices(EXPRESSIONS), value=numeric,
    )
    camera = obj(time=numeric, shot=choices(["wide", "medium", "close", "detail"]), focus_id=string, pan=numeric)
    speech = obj(track=choices(["narration", "dialogue"]), speaker_id=string, text=string, start=numeric)
    scene = obj(
        scene_title=string, duration=numeric, environment=choices(ENVIRONMENTS),
        lighting=choices(["day", "night", "warm", "memory"]), character_ids=array(string),
        actors=array(actor), props=array(prop), actions=array(action), camera=array(camera),
        speech=array(speech), sounds=array(obj(type=choices(SOUNDS), at=numeric)),
        transition=choices(["cut", "dissolve", "dip"]),
    )
    character = obj(
        id=string, name=string, personality=string, role=string, appearance=appearance,
        species=choices(["human", "fox", "cat", "dog", "rabbit", "bear", "owl", "robot"]),
        voice_type=choices(["female", "male", "child", "elder", "neutral"]),
    )
    return obj(
        schema_version={"type": "integer", "enum": [STORY_VERSION]},
        title=string, summary=string,
        mood=choices(["suspense", "gentle", "playful", "adventure", "sad"]),
        characters=array(character), scenes=array(scene),
    )


def number(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if not math.isfinite(result):
        raise StoryValidationError("Storyboard numbers must be finite.")
    return round(min(hi, max(lo, result)), 4)


def ident(value: Any, default: str = "") -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or default))[:48].strip("-") or default


def color(value: Any, default: str) -> str:
    value = str(value or "")
    return value if re.fullmatch(r"#[a-fA-F0-9]{6}", value) else default


def point(value: Any, default: tuple[float, float] = (.5, .82)) -> dict:
    value = value if isinstance(value, dict) else {}
    return {"x": number(value.get("x"), default[0], .08, .92), "y": number(value.get("y"), default[1], .25, .9)}


def _repair_prop_supports(scene: dict, previous_scene: dict) -> None:
    props = scene.get("props")
    if not isinstance(props, list) or any(not isinstance(prop, dict) for prop in props):
        return
    prop_by_id = {
        ident(prop.get("id"), f"prop-{index + 1}"): prop
        for index, prop in enumerate(props[:MAX_SCENE_PROPS])
    }
    support_by_id = {pid: ident(prop.get("support_id")) for pid, prop in prop_by_id.items()}
    previous_props = previous_scene.get("props")
    previous_props = previous_props[:MAX_SCENE_PROPS] if isinstance(previous_props, list) else []
    previous_supports = {
        ident(prop.get("id"), f"prop-{index + 1}"): prop
        for index, prop in enumerate(previous_props)
        if isinstance(prop, dict) and prop.get("type") in PROP_SUPPORTS and not prop.get("support_id")
    }
    for prop_id, prop in list(prop_by_id.items()):
        support_id = support_by_id[prop_id]
        if not support_id:
            continue

        # The renderer anchors objects to furniture. A container such as a box
        # can share its furniture anchor with the object it contains.
        visited = {prop_id}
        anchor = prop
        while support_id in support_by_id and support_by_id[support_id] and support_id not in visited:
            visited.add(support_id)
            anchor = prop_by_id[support_id]
            support_id = support_by_id[support_id]
        if support_id in visited:
            support_id = ""
        support = prop_by_id.get(support_id)
        if support is None and support_id:
            replacement = previous_supports.get(support_id)
            if replacement is None and support_id in PROP_SUPPORTS:
                matches = [
                    pid for pid, candidate in prop_by_id.items()
                    if pid not in visited and candidate.get("type") == support_id and not support_by_id[pid]
                ]
                if len(matches) == 1:
                    support_id = matches[0]
                    support = prop_by_id[support_id]
                elif not matches and anchor.get("type") not in PROP_SUPPORTS:
                    replacement = {"id": support_id, "type": support_id, "x": anchor.get("x"), "y": .82}
            if replacement is not None and len(props) < MAX_SCENE_PROPS:
                support = {**replacement, "id": support_id}
                props.append(support)
                prop_by_id[support_id] = support
                support_by_id[support_id] = ""

        if support is not None and support.get("type") in PROP_SUPPORTS:
            prop["support_id"] = support_id
        else:
            # Leave the object and its actions intact at the floor anchor.
            prop["support_id"] = None
            prop["y"] = .82


def _repair_box_reveal(scene: dict, previous_scene: dict) -> None:
    """Restore a clear box-to-item reveal when the director skipped the lid."""
    props = scene.get("props")
    actions = scene.get("actions")
    if (not isinstance(props, list) or not isinstance(actions, list)
            or any(not isinstance(item, dict) for item in [*props, *actions])):
        return
    if any(action.get("type") == "open_box" for action in actions):
        return
    boxes = [p for p in props if p.get("type") == "box"]
    restore_box = not boxes
    if restore_box:
        boxes = [p for p in previous_scene.get("props", []) if p.get("type") == "box"]
    if len(boxes) != 1 or (restore_box and len(props) >= MAX_SCENE_PROPS) or len(actions) >= 80:
        return
    box = boxes[0]
    old_props = {ident(p.get("id")) for p in previous_scene.get("props", [])}
    contents = {
        ident(prop.get("id")): prop for prop in props
        if prop.get("type") in BOX_CONTENTS
        and (not restore_box or ident(prop.get("id")) not in old_props)
        and ident(prop.get("support_id")) == ident(box.get("support_id"))
        and abs(point(prop)["x"] - point(box)["x"]) <= .12
    }
    pickups = [a for a in actions if a.get("type") == "pick_up" and ident(a.get("target_id")) in contents]
    if len(pickups) != 1:
        return
    pick = pickups[0]
    led = contents[ident(pick["target_id"])]
    box_id = ident(box.get("id"))
    if (not box_id or box.get("state") == "open" or led.get("holder_id")
            or (restore_box and any(ident(p.get("id")) == box_id for p in props))):
        return
    end = number(pick.get("end"), 0, 0, scene["duration"])
    start = number(pick.get("start"), 0, 0, end)
    if end < 1.25:
        return
    pickup_start = max(1.1, start)
    if pickup_start >= end - .2:
        return
    if restore_box:
        props.append(dict(box))
    led["reveal_from_id"] = box_id
    pick["start"] = pickup_start
    actions.append({"type": "open_box", "character_id": pick["character_id"],
                    "target_id": box_id, "start": pickup_start - 1.1, "end": pickup_start - .35})
    camera = scene.get("camera")
    if isinstance(camera, list) and all(isinstance(key, dict) for key in camera):
        open_start = pickup_start - 1.1
        closeup = {"time": open_start, "shot": "detail", "focus_id": box_id}
        scene["camera"] = [
            *[key for key in camera if number(key.get("time"), 0, 0, scene["duration"]) < open_start],
            closeup,
            {**closeup, "time": pickup_start},
            *[key for key in camera if number(key.get("time"), 0, 0, scene["duration"]) > pickup_start],
        ]
    for actor in scene.get("actors") or []:
        if not isinstance(actor, dict) or actor.get("character_id") != pick["character_id"]:
            continue
        box_x = point(box)["x"]
        actor_x = point(actor)["x"]
        has_approach = any(a.get("character_id") == pick["character_id"] and a.get("type") in {"walk", "run"}
                           for a in actions)
        if not has_approach and abs(actor_x - box_x) < .13:
            offset = -.15 if box_x >= .25 else .15
            actor["x"] = round(box_x + offset, 4)


def prepare_director_reply(raw: dict, *, prompt: str = "") -> dict:
    """Repair model timing and prop placement before validating a new reply."""
    story = copy.deepcopy(raw)
    start = 0.0
    previous_scene = {}
    requests_box_opening = bool(re.search(
        r"\b(?:open(?:s|ed|ing)?|lift(?:s|ed|ing)?)\b[^.!?]{0,38}\b(?:box|chest|sandook)\b",
        prompt, re.IGNORECASE,
    ))
    for scene in story.get("scenes", []):
        if not isinstance(scene, dict):
            break  # The validator reports malformed scenes.
        duration = scene.get("duration")
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            break
        same_location = (
            scene.get("environment") == previous_scene.get("environment")
            and (scene.get("lighting") == "memory") == (previous_scene.get("lighting") == "memory")
        )
        _repair_prop_supports(scene, previous_scene if same_location else {})
        actions = scene.get("actions") or []
        action_times = [action[key] for action in actions for key in ("start", "end")
                        if isinstance(action, dict) and key in action]
        # Require evidence that the whole action group uses video time.
        if (start > 0 and action_times
                and all(isinstance(t, (int, float)) and start <= t <= start + duration for t in action_times)
                and any(t > duration for t in action_times)):
            for field, keys in (("actions", ("start", "end")), ("camera", ("time",)),
                                ("speech", ("start",)), ("sounds", ("at",))):
                times = [(item, key) for item in scene.get(field) or [] if isinstance(item, dict)
                         for key in keys if key in item]
                if all(isinstance(item[key], (int, float)) and start <= item[key] <= start + duration
                       for item, key in times):
                    for item, key in times:
                        item[key] = round(item[key] - start, 4)
        if requests_box_opening:
            _repair_box_reveal(scene, previous_scene if same_location else {})
        previous_scene = scene
        start += duration
    return story


def normalize_director_story(raw: dict, *, duration: int, scene_lengths: tuple[int, ...] = ()) -> dict:
    """Reject dangling identities/unsupported verbs; normalize bounded numeric data."""
    if not 5 <= duration <= 120:
        raise StoryValidationError("Story duration must be between 5 and 120 seconds.")
    characters = []
    for i, item in enumerate(raw.get("characters", [])[:4]):
        if not isinstance(item, dict):
            raise StoryValidationError("Each character must be an object.")
        app = item.get("appearance") if isinstance(item.get("appearance"), dict) else {}
        characters.append({
            "id": ident(item.get("id"), f"actor-{i+1}"), "name": str(item.get("name") or f"Actor {i+1}")[:60],
            "role": str(item.get("role") or "")[:160], "personality": str(item.get("personality") or "")[:160],
            "species": item.get("species") if item.get("species") in {"human", "fox", "cat", "dog", "rabbit", "bear", "owl", "robot"} else "human",
            "voice_type": item.get("voice_type") if item.get("voice_type") in {"male", "female", "child", "elder", "neutral"} else "neutral",
            "rig": "biped-v3",
            "appearance": {
                **{k: color(app.get(k), v) for k, v in {"skin_color": "#CAA087", "hair_color": "#1B2434", "shirt_color": "#327C83", "pants_color": "#284F64", "shoe_color": "#182B3B", "eye_color": "#4B3835"}.items()},
                "hair_style": app.get("hair_style") if app.get("hair_style") in {"short", "long", "curly", "spiky", "bald"} else "short",
                "clothing": app.get("clothing") if app.get("clothing") in {"shirt", "kameez", "dress", "jacket"} else "shirt",
                "face_shape": app.get("face_shape") if app.get("face_shape") in {"oval", "round", "angular"} else "oval",
                "body_scale": number(app.get("body_scale"), 1, .75, 1.2),
            },
        })
    ids = {c["id"] for c in characters}
    if not characters or len(ids) != len(characters):
        raise StoryValidationError("Characters require unique stable IDs.")
    source_scenes = raw.get("scenes", [])
    if not isinstance(source_scenes, list) or not 1 <= len(source_scenes) <= 12:
        raise StoryValidationError("Provide 1 to 12 directed scenes.")
    weights = [number(s.get("duration"), duration / len(source_scenes), .5, 120) for s in source_scenes if isinstance(s, dict)]
    if len(weights) != len(source_scenes):
        raise StoryValidationError("Each scene must be an object.")
    scale = duration / sum(weights)
    scenes, start = [], 0.0
    carried_layers: dict[str, dict] = {"present": {}, "memory": {}}
    for i, (source, weight) in enumerate(zip(source_scenes, weights)):
        length = scene_lengths[i] if scene_lengths else (
            round(weight * scale, 4) if i < len(weights)-1 else round(duration-start, 4)
        )
        factor = length / weight
        carried = carried_layers["memory" if source.get("lighting")=="memory" else "present"]
        scene_ids = source.get("character_ids") or [c["id"] for c in characters]
        if not isinstance(scene_ids, list) or any(not isinstance(cid, str) for cid in scene_ids):
            raise StoryValidationError("Scene character IDs must be strings.")
        scene_ids = [ident(cid.strip()) for cid in scene_ids]
        if any(cid not in ids for cid in scene_ids) or len(set(scene_ids)) != len(scene_ids):
            raise StoryValidationError("A scene references unknown or duplicate characters.")
        poses = source.get("actors") if isinstance(source.get("actors"), list) else []
        actors = []
        for j, cid in enumerate(scene_ids):
            actor = next((a for a in poses if isinstance(a, dict) and ident(a.get("character_id")) == cid), {})
            actors.append({"character_id": cid, **point(actor, ((j+1)/(len(scene_ids)+1), .82)),
                           "pose": actor.get("pose") if actor.get("pose") in {"stand", "sit", "sleep"} else "stand",
                           "facing": number(actor.get("facing"), 1, -1, 1), "scale": number(actor.get("scale"), 1, .7, 1.15)})
        props = []
        for j, prop in enumerate((source.get("props") or [])[:MAX_SCENE_PROPS]):
            if not isinstance(prop, dict) or prop.get("type") not in PROPS:
                raise StoryValidationError("Unknown prop type.")
            props.append({"id": ident(prop.get("id"), f"prop-{j+1}"), "type": prop["type"], **point(prop, (.78, .82)),
                          "state": "open" if prop.get("state") == "open" else "closed", "color": color(prop.get("color"), "#947666"),
                          "support_id": ident(prop.get("support_id")) or None, "holder_id": ident(prop.get("holder_id")) or None,
                          **({"reveal_from_id": ident(prop["reveal_from_id"])} if prop.get("reveal_from_id") and not prop.get("holder_id") else {})})
        for pid,(prop,holder) in carried.items():
            if holder in scene_ids:
                current=next((p for p in props if p["id"]==pid),None)
                if current and current["type"]!=prop["type"]:
                    raise StoryValidationError("A carried prop cannot change its design between scenes.")
                if current is None:
                    placed = {key: value for key, value in prop.items() if key != "reveal_from_id"}
                    props.append({**placed, "holder_id": holder, "support_id": None})
                elif not current["holder_id"] and not any(
                    isinstance(action, dict) and action.get("type") == "pick_up" and ident(action.get("target_id")) == pid
                    for action in source.get("actions") or []
                ):
                    current["holder_id"] = holder
                    current.pop("reveal_from_id", None)
        pids = {p["id"] for p in props}
        if len(pids) != len(props):
            raise StoryValidationError("Prop IDs must be unique per scene.")
        for prop in props:
            if prop["holder_id"] and prop["holder_id"] not in scene_ids:
                raise StoryValidationError("A prop holder must be visible in its scene.")
            if prop["support_id"] and not any(p["id"]==prop["support_id"] and p["type"] in PROP_SUPPORTS and not p["support_id"] for p in props):
                raise StoryValidationError("A supported object requires an existing table, bed or chair.")
        actions = []
        for item in (source.get("actions") or [])[:80]:
            if not isinstance(item, dict) or item.get("type") not in ACTIONS:
                raise StoryValidationError("Unsupported animation action. Use a supported director verb.")
            cid = ident(item.get("character_id"))
            target = ident(item.get("target_id")) or None
            openable_type = OPENABLE_ACTIONS.get(item["type"])
            if target is None and openable_type:
                openable = [prop["id"] for prop in props if prop["type"] == openable_type]
                if len(openable) == 1:
                    target = openable[0]
            if cid not in scene_ids or (target and target not in pids and target not in scene_ids):
                raise StoryValidationError("An action references a missing actor or target.")
            at = number(item.get("start"), 0, 0, weight) * factor
            end = number(item.get("end"), weight, 0, weight) * factor
            if end <= at:
                raise StoryValidationError("Actions need a positive duration within their scene.")
            if (item["type"] in {"pick_up", "put_down"} or openable_type) and target not in pids:
                raise StoryValidationError("Object interaction requires a scene prop.")
            if openable_type and next(p for p in props if p["id"] == target)["type"] != openable_type:
                message = "Door actions require a door prop." if openable_type == "door" else "Box actions require a box prop."
                raise StoryValidationError(message)
            actions.append({"type": item["type"], "character_id": cid, "start": round(at,4), "end": round(end,4),
                            "target_id": target, "to": point(item.get("to"), (.65,.82)) if item.get("to") else None,
                            "expression": item.get("expression") if item.get("expression") in EXPRESSIONS else "neutral",
                            "value": number(item.get("value"), 1, -1, 1)})
        if not actions:
            raise StoryValidationError("Each scene needs executable timed actions.")
        opening_boxes = {a["target_id"] for a in actions if a["type"] == "open_box"}
        open_boxes = {p["id"] for p in props if p["type"] == "box" and p["state"] == "open"}
        for prop in props:
            if prop.get("reveal_from_id") and (
                prop["type"] not in BOX_CONTENTS
                or prop["reveal_from_id"] not in (opening_boxes | open_boxes)
            ):
                raise StoryValidationError("A revealed item requires a box that opens in the scene.")
        cameras = []
        for c in (source.get("camera") or [{"time": 0, "shot": "wide"}, {"time": weight, "shot": "medium"}])[:16]:
            if not isinstance(c, dict):
                raise StoryValidationError("Camera keyframes must be objects.")
            focus = ident(c.get("focus_id")) or scene_ids[0]
            if focus not in scene_ids and focus not in pids:
                raise StoryValidationError("Camera focus references a missing actor or prop.")
            cameras.append({"time": number(c.get("time"), 0, 0, weight)*factor,
                            "shot": c.get("shot") if c.get("shot") in {"wide","medium","close","detail"} else "wide",
                            "focus_id": focus, "pan": number(c.get("pan"), 0, -.12, .12)})
        environment = source.get("environment") or "forest"
        if environment not in ENVIRONMENTS:
            raise StoryValidationError("Unsupported environment.")
        speech = []
        for j, line in enumerate((source.get("speech") or [])[:16]):
            if not isinstance(line, dict):
                raise StoryValidationError("Speech must be structured.")
            track = "narration" if line.get("track") == "narration" else "dialogue"
            speaker = ident(line.get("speaker_id")) or (scene_ids[0] if track == "dialogue" else "narrator")
            start_at = round(number(line.get("start"), .4, 0, weight) * factor, 4)
            if track == "dialogue" and speaker == "narrator":
                speaking = {
                    action["character_id"] for action in actions
                    if action["type"] == "speak" and action["start"] <= start_at < action["end"]
                }
                if len(speaking) == 1:
                    speaker = next(iter(speaking))
            if track == "dialogue" and speaker not in scene_ids:
                raise DialogueSpeakerError("Dialogue must belong to a visible character.")
            if speaker != "narrator" and speaker not in scene_ids:
                raise StoryValidationError("Speech references a missing character.")
            text = str(line.get("text") or "").strip()[:600]
            if text:
                speech.append({"id": f"scene-{i+1}-line-{j+1}", "track": track, "speaker_id": speaker, "text": text,
                               "start": start_at})
        sounds = []
        for sound in (source.get("sounds") or [])[:24]:
            if not isinstance(sound, dict) or sound.get("type") not in SOUNDS:
                raise StoryValidationError("Unsupported sound cue.")
            sounds.append({"type": sound["type"], "at": number(sound.get("at"),0,0,weight)*factor})
        lighting = source.get("lighting") if source.get("lighting") in {"day","night","warm","memory"} else "day"
        for prop in props:
            holder=prop["holder_id"]
            for action in sorted(actions,key=lambda a:a["end"]):
                if action["target_id"]==prop["id"]:
                    if action["type"]=="pick_up":holder=action["character_id"]
                    elif action["type"]=="put_down":holder=None
            if holder:carried[prop["id"]]=(prop,holder)
            else:carried.pop(prop["id"],None)
        scenes.append({"id": f"scene-{i+1}", "scene_title": str(source.get("scene_title") or "")[:80],
                       "start": round(start,4), "duration": length, "environment": environment, "lighting": lighting,
                       "character_ids": scene_ids, "actors": actors, "props": props, "actions": sorted(actions,key=lambda a:a["start"]),
                       "camera": sorted(cameras,key=lambda c:c["time"]), "speech": speech, "sounds": sounds,
                       "transition": source.get("transition") if source.get("transition") in {"cut","dissolve","dip"} else "cut"})
        start += length
    return {"schema_version": 3, "title": str(raw.get("title") or "Animated story")[:100], "summary": str(raw.get("summary") or "")[:400],
            "mood": raw.get("mood") if raw.get("mood") in {"suspense","gentle","playful","adventure","sad"} else "gentle",
            "characters": characters, "scenes": scenes, "duration": duration}


def director_prompt(duration: int, language: str, style: str, prompt: str) -> str:
    return f"""Direct a {duration}-second original animated story in {language}, visual style {style}.
USER IDEA: {prompt}
Return a JSON object with schema_version:3, title, summary, mood, characters and scenes.
Characters: 1-4 unique stable id, name, personality, role, species (human/fox/cat/dog/rabbit/bear/owl/robot),
voice_type (female/male/child/elder/neutral), appearance:
skin_color,hair_color,shirt_color,pants_color,shoe_color,eye_color (#RRGGBB),
hair_style (short/long/curly/spiky/bald), clothing (shirt/kameez/dress/jacket), face_shape (oval/round/angular), body_scale (.75-1.2).
Scenes: duration in seconds (sum exactly {duration}), environment from {sorted(ENVIRONMENTS)}.
All action start/end, camera time, speech start, and sound at values are local to their scene.
For example, an action one second into the second scene has start 1, even if that scene starts at video time 10.
Every action must satisfy 0 <= start < end <= scene duration.
Use the same exact lowercase ASCII IDs in every reference. Each scene needs a visible actor and at least one action.
List a prop in every scene where an action or camera refers to it, even if it appeared earlier. Keep the same prop ID, type and hex color across cuts. Set color to the requested #RRGGBB. Use a timed put_down when an actor stops carrying it.
Use null for unused action targets and positions and empty arrays for unused props, speech, or sounds.
Loose objects rest on the floor at y .82, or set support_id to a table/bed/chair ID; the renderer places them on its surface.
Each support_id must name a table, bed or chair declared in that same scene's props with its own support_id set to null.
For a box reveal, list both props in the scene, sharing the same furniture support or floor position. Use open_box with the box ID, then pick_up with the item ID. Set the item's reveal_from_id to the box ID so it stays hidden until the lid opens. Set reveal_from_id to null for all other props.
Positions are normalized 0.08-0.92, y is the floor/feet anchor. Place sleeping actors with their hip on a bed.
Supported action types: {sorted(ACTIONS)}. Express story beats with the closest supported actions and props.
For example, an envelope can be a letter prop. Suggest complex or offscreen events through sound, framing, and reaction.
Persistent poses stay until changed.
Use target_id for picking up/putting down props and opening/closing doors. Reaching/pickup actors must walk within .15 x of target first.
Stage the actor slightly to the side of a prop so their body does not block the reveal. Frame the box as it opens, then cut or move to the character's reaction.
Only walk/run change position using "to". React sets expression; look/turn/head use value -1 to 1.
Camera focus_id must refer to a visible actor or prop. Keep interactions in wide/medium shots so hands and props remain visible.
Use speaker_id "narrator" only on the narration track. For dialogue, put the speaker's exact ID in the scene's character_ids, include a visible actor for that ID, and align a speak action with the line. When a character is revealed at a door, stage them visibly before their dialogue starts.
Sound types: {sorted(SOUNDS)}.
Use only as many scenes as the story needs (typically 1-3 for a 15-second story). Keep a location for continuity when appropriate.
Do not invent dialogue for silent beats. Include narration when the user requests it.
Use the requested script: Urdu in Urdu script/RTL, Hindi in Devanagari/LTR, Hinglish in Roman/LTR.
Keep speech concise enough to fit after its start, with at least .25s between voices. No simultaneous narration and dialogue.
Preserve user-supplied dialogue verbatim when it fits. Prefer one short line over several in a brief scene.
Use each quoted line exactly as often as it occurs in the brief. Keep its speaker and requested time range. Do not repeat a later line as earlier narration or speak a reaction before the event that causes it.
Show a recognizable story action or object in the first two seconds. Use the final shot to show the requested outcome or cliffhanger. Finish the final action in time to hold on its result.
For a dog wagging its tail, use wag for the dog actor. Keep the exact requested species in the character data.
Plan an opening event, a visible response, and a final image or payoff. For a detailed brief, preserve its key beats and requested ending. Show the action that causes a reveal and then show its visible result.
No executable code, URLs, markdown, generic action sentences or unsupported motion descriptions. JSON only."""

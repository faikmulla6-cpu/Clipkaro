"""Apply explicit script and staging constraints before speech is generated."""
from __future__ import annotations

from collections import defaultdict
import re
import unicodedata

from .cartoon_story import PROP_COLORS, PROPS


_QUOTED_LINE = re.compile(r'“([^”]+)”|"([^"]+)"')
_BEAT_RANGE = re.compile(r"\b(\d{1,3})\s*[–—-]\s*(\d{1,3})\s*(?:seconds?|secs?|s)\b", re.IGNORECASE)
_PROP_DESCRIPTION = re.compile(
    r"\b(" + "|".join(PROP_COLORS) + r")\s+(" + "|".join(sorted(PROPS)) + r")\b", re.IGNORECASE,
)


def scripted_scene_lengths(prompt: str, duration: int) -> tuple[int, ...]:
    ranges = [(int(match[1]), int(match[2])) for match in _BEAT_RANGE.finditer(prompt)]
    if not 2 <= len(ranges) <= 12 or ranges[-1][1] != duration:
        return ()
    boundary = 0
    for start, end in ranges:
        if start != boundary or end <= start:
            return ()
        boundary = end
    return tuple(end - start for start, end in ranges)


def _speech_key(text: str) -> str:
    # Normalize punctuation and apostrophes without stripping combining marks in
    # languages such as Hindi and Urdu.
    canonical = unicodedata.normalize("NFC", text).casefold()
    return " ".join("".join(c for c in canonical if not unicodedata.category(c).startswith("P")).split())


def _preserve_quoted_lines(story: dict, prompt: str) -> None:
    requested = defaultdict(list)
    ranges = list(_BEAT_RANGE.finditer(prompt))
    previous_quote_end = 0
    for match in _QUOTED_LINE.finditer(prompt):
        line = (match[1] or match[2]).strip()
        beat = next((span for span in reversed(ranges) if span.end() <= match.start()), None)
        window = (int(beat[1]), int(beat[2])) if beat and int(beat[1]) < int(beat[2]) else None
        before_line = prompt[max(beat.end() if beat else 0, previous_quote_end):match.start()]
        previous_quote_end = match.end()
        after_pickup = bool(re.search(r"\bpick(?:s|ed|ing)?\b[^.!?]{0,30}\bup\b", before_line, re.IGNORECASE))
        if key := _speech_key(line):
            requested[key].append((line, window, after_pickup))

    candidates = defaultdict(list)
    for scene in story["scenes"]:
        for line in scene["speech"]:
            candidates[_speech_key(line["text"])].append((scene["start"] + line["start"], scene, line))

    discarded = set()
    for key, occurrences in requested.items():
        remaining = sorted(candidates[key], key=lambda entry: entry[0])
        retained = 0
        for exact_text, window, after_pickup in sorted(occurrences, key=lambda occurrence: occurrence[1] is None):
            if not remaining:
                break
            # Reserve timed occurrences first so an early duplicate cannot take the reveal line.
            matching = [i for i, (at, _, _) in enumerate(remaining) if not window or window[0] <= at < window[1]]
            if not matching:
                continue
            index = matching[0]
            if after_pickup:
                for candidate in matching:
                    _, candidate_scene, candidate_line = remaining[candidate]
                    if any(a["type"] == "pick_up" and a["character_id"] == candidate_line["speaker_id"]
                           for a in candidate_scene["actions"]):
                        index = candidate
                        break
            _, scene, line = remaining.pop(index)
            line["text"] = exact_text
            if after_pickup and len(occurrences) == 1:
                pickups = [a for a in scene["actions"] if a["type"] == "pick_up" and a["character_id"] == line["speaker_id"]]
                if len(pickups) == 1 and pickups[0]["end"] <= scene["duration"] - 1.5:
                    line["start"] = max(line["start"], pickups[0]["end"])
            retained += 1
        if retained == len(occurrences):
            discarded.update(line["id"] for _, _, line in remaining)
    for scene in story["scenes"]:
        scene["speech"] = [line for line in scene["speech"] if line["id"] not in discarded]


def _apply_named_colors(story: dict, prompt: str) -> None:
    colors = defaultdict(set)
    for color, prop_type in _PROP_DESCRIPTION.findall(prompt.casefold()):
        colors[prop_type].add(color)
    for prop_type, names in colors.items():
        if len(names) != 1:
            continue
        name = next(iter(names))
        props = [prop for scene in story["scenes"] for prop in scene["props"] if prop["type"] == prop_type]
        ids = {prop["id"] for prop in props}
        exact = {pid for pid in ids if pid.casefold().replace("-", "_") == f"{name}_{prop_type}"}
        target_ids = exact if len(exact) == 1 else ids if len(ids) == 1 else set()
        for prop in props:
            if prop["id"] in target_ids:
                prop["color"] = PROP_COLORS[name]


def _stage_bookends(story: dict, prompt: str) -> None:
    first, last = story["scenes"][0], story["scenes"][-1]
    opening = first["actions"][0]
    if opening["type"] == "idle" and opening["start"] == 0 and opening["end"] >= 1.25:
        visible = {p["id"] for p in first["props"] if not p.get("reveal_from_id")}
        focus = next((a for a in first["actions"] if a["type"] in {"look", "reach", "point"}
                      and a["character_id"] == opening["character_id"] and a["target_id"] in visible), None)
        if focus and first["camera"][0]["focus_id"] not in visible:
            opening.update(type="head", value=.55)
            first["camera"][0].update(shot="close", focus_id=focus["target_id"])

    closing = last["actions"][-1]
    if closing["type"] == "jump" and closing["end"] >= last["duration"] - .1 and closing["end"] - closing["start"] >= 1.5:
        closing["end"] = round(closing["start"] + .85, 4)
        key = last["camera"][-1]
        if key["focus_id"] == closing["character_id"] and key["time"] >= closing["start"] - .25:
            key["shot"] = "medium"
    dogs = {c["id"] for c in story["characters"] if c["species"] == "dog"} & set(last["character_ids"])
    if (len(dogs) == 1 and len(last["actions"]) < 80 and re.search(r"\bwag\w*\b[^.!?]{0,20}\btail\b", prompt, re.IGNORECASE)
            and not any(action["type"] == "wag" for action in last["actions"])):
        last["actions"].append({
            "type": "wag", "character_id": next(iter(dogs)), "start": 0, "end": last["duration"],
            "target_id": None, "to": None, "expression": "neutral", "value": 1,
        })
        last["actions"].sort(key=lambda action: action["start"])


def direct_story(story: dict, prompt: str) -> dict:
    _preserve_quoted_lines(story, prompt)
    _apply_named_colors(story, prompt)
    _stage_bookends(story, prompt)
    if re.search(r"\bcreak\b", prompt, re.IGNORECASE):
        for scene in story["scenes"]:
            opening = next((a for a in scene["actions"] if a["type"] == "open_box"), None)
            if opening and len(scene["sounds"]) < 24 and not any(cue["type"] == "door_creak" for cue in scene["sounds"]):
                scene["sounds"].append({"type": "door_creak", "at": opening["start"]})
    return story

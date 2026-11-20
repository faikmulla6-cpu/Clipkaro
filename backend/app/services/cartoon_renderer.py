from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from app.services.cartoon_timing import build_karaoke_caption_markup


RATIOS = {
    "9:16": (1080, 1920, "portrait"),
    "16:9": (1920, 1080, "landscape"),
    "1:1": (1080, 1080, "square"),
}
PALETTES = {
    "forest": ("#9BE4CF", "#D8F5C6", "#4F9B70", "#245C46"),
    "city": ("#9BCBFA", "#E7F1FF", "#7B91A8", "#394D65"),
    "beach": ("#8DDCF4", "#FFE4A6", "#F3C56B", "#2E9AB2"),
    "space": ("#101A46", "#343D78", "#5964A8", "#171F4E"),
    "castle": ("#D8C1F6", "#F4E8FF", "#A58ACD", "#65518E"),
    "school": ("#B8DDF5", "#F7E8C7", "#C7A16E", "#86633E"),
    "home": ("#F2D6C2", "#FFF0D8", "#C78F78", "#8A5747"),
    "mountain": ("#A8D5F4", "#E5F4FF", "#7FA68A", "#496B61"),
    "desert": ("#F6C27C", "#FFE5B5", "#D99B56", "#9A653C"),
    "garden": ("#BDEAA8", "#F1FFD9", "#75B65D", "#397849"),
}


def _text(value: Any, limit: int = 240) -> str:
    return html.escape(str(value or "").strip()[:limit], quote=True)


def _id(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or ""))[:36].strip("-")
    return cleaned or fallback


def _color(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate) else fallback


def _palette(environment: Any) -> tuple[str, str, str, str]:
    return PALETTES.get(str(environment or "").lower(), PALETTES["forest"])


def _background_svg(environment: str, width: int, height: int, index: int) -> str:
    sky, glow, hill, ground = _palette(environment)
    env = _id(environment, "forest")
    sun = "#FFF2B0" if env != "space" else "#D9C9FF"
    trees = ""
    if env in {"forest", "garden"}:
        trees = (
            f'<g opacity=".95"><path d="M{width*.12} {height*.77}v-{height*.25}" stroke="#6B4C37" stroke-width="30"/>'
            f'<circle cx="{width*.12}" cy="{height*.49}" r="{width*.09}" fill="#34845D"/>'
            f'<path d="M{width*.82} {height*.78}v-{height*.28}" stroke="#6B4C37" stroke-width="34"/>'
            f'<circle cx="{width*.82}" cy="{height*.46}" r="{width*.1}" fill="#2E7656"/></g>'
        )
    elif env == "city":
        blocks = []
        for i, (x, w, h) in enumerate(((.05,.12,.28),(.2,.14,.4),(.39,.12,.32),(.57,.16,.48),(.78,.13,.34))):
            blocks.append(f'<rect x="{width*x}" y="{height*(.72-h)}" width="{width*w}" height="{height*h}" rx="12" fill="{("#647D9B","#8299B3","#526C89")[i%3]}"/>')
        trees = "".join(blocks)
    elif env == "space":
        stars = []
        for x, y, r in ((.12,.18,5),(.28,.3,4),(.78,.2,6),(.9,.42,4),(.62,.12,3),(.4,.14,4)):
            stars.append(f'<circle cx="{width*x}" cy="{height*y}" r="{r}" fill="#FFFFFF" opacity=".85"/>')
        trees = "".join(stars) + f'<circle cx="{width*.78}" cy="{height*.45}" r="{width*.12}" fill="#8A75CE" opacity=".55"/>'
    elif env == "castle":
        trees = (
            f'<path d="M{width*.12} {height*.72}v-{height*.22}h{width*.18}v{height*.22} M{width*.1} {height*.5}l{width*.11}-{height*.13} {width*.11} {height*.13}" fill="#9B7BC7"/>'
            f'<path d="M{width*.72} {height*.72}v-{height*.25}h{width*.18}v{height*.25} M{width*.7} {height*.47}l{width*.11}-{height*.13} {width*.11} {height*.13}" fill="#9B7BC7"/>'
        )
    else:
        trees = f'<path d="M0 {height*.75} Q{width*.25} {height*.59} {width*.5} {height*.75} T{width} {height*.73} V{height} H0Z" fill="{hill}"/>'
    cloud = (
        f'<g fill="#FFFFFF" opacity=".72"><ellipse cx="{width*.25}" cy="{height*.22}" rx="{width*.07}" ry="{height*.025}"/>'
        f'<ellipse cx="{width*.28}" cy="{height*.205}" rx="{width*.045}" ry="{height*.03}"/>'
        f'<ellipse cx="{width*.68}" cy="{height*.29}" rx="{width*.08}" ry="{height*.025}"/></g>'
    ) if env != "space" else ""
    return (
        f'<svg class="scene-bg" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">'
        f'<defs><linearGradient id="sky-{index}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky}"/>'
        f'<stop offset="1" stop-color="{glow}"/></linearGradient></defs>'
        f'<rect width="{width}" height="{height}" fill="url(#sky-{index})"/>'
        f'<circle cx="{width*.82}" cy="{height*.16}" r="{width*.055}" fill="{sun}" opacity=".92"/>'
        f'{cloud}{trees}'
        f'<path d="M0 {height*.79} Q{width*.22} {height*.68} {width*.42} {height*.8} T{width} {height*.77} V{height} H0Z" fill="{hill}"/>'
        f'<path d="M0 {height*.88} Q{width*.3} {height*.78} {width*.55} {height*.9} T{width} {height*.86} V{height} H0Z" fill="{ground}"/>'
        f'</svg>'
    )


def _character_svg(character: dict[str, Any], uid: str, expression: str, style: str) -> str:
    appearance = character.get("appearance") if isinstance(character.get("appearance"), dict) else {}
    skin = _color(appearance.get("skin_color"), "#E9B58F")
    hair = _color(appearance.get("hair_color"), "#3D2A25")
    shirt = _color(appearance.get("shirt_color"), "#E87552")
    pants = _color(appearance.get("pants_color"), "#405D86")
    shoe = _color(appearance.get("shoe_color"), "#3A3441")
    hair_style = str(appearance.get("hair_style") or "short").lower()
    species = str(character.get("species") or "human").lower()
    if species not in {"human", "fox", "cat", "dog", "rabbit", "bear", "owl", "robot"}:
        species = "human"
    eye_r = 13 if style == "anime-inspired" else 10
    mouth_y = 224
    if expression == "sad":
        mouth = f'<path id="{uid}-mouth" d="M150 230 Q180 202 210 230" stroke="#652D36" stroke-width="9" fill="none" stroke-linecap="round"/>'
    elif expression == "surprised":
        mouth = f'<ellipse id="{uid}-mouth" cx="180" cy="{mouth_y}" rx="15" ry="18" fill="#652D36"/>'
    elif expression == "angry":
        mouth = f'<path id="{uid}-mouth" d="M151 222 Q180 218 209 222" stroke="#652D36" stroke-width="9" fill="none" stroke-linecap="round"/>'
    else:
        mouth = f'<path id="{uid}-mouth" d="M148 215 Q180 247 212 215" stroke="#652D36" stroke-width="9" fill="none" stroke-linecap="round"/>'

    ear_markup = ""
    tail_markup = ""
    muzzle_markup = ""
    nose_markup = ""
    whiskers_markup = ""
    brow = "#4A3029"
    head_shape = f'<ellipse cx="180" cy="153" rx="91" ry="106" fill="{skin}" stroke="#6D493E" stroke-opacity=".22" stroke-width="5"/>'
    hair_shape = ""

    if species == "human":
        if hair_style == "long":
            hair_shape = f'<path d="M91 152 Q77 38 180 42 Q288 36 270 164 L260 285 L231 260 L230 130 Q180 88 126 132 L120 276 L94 288Z" fill="{hair}"/>'
        elif hair_style == "curly":
            hair_shape = f'<path d="M91 151 Q72 56 126 52 Q143 18 176 43 Q212 8 240 54 Q292 58 270 158 Q236 115 180 112 Q126 115 91 151Z" fill="{hair}"/>'
        elif hair_style == "spiky":
            hair_shape = f'<path d="M91 145 L102 76 L133 101 L151 42 L178 91 L208 35 L219 100 L260 69 L270 150 Q180 102 91 145Z" fill="{hair}"/>'
        elif hair_style != "bald":
            hair_shape = f'<path d="M91 151 Q80 55 180 45 Q278 52 269 151 Q224 111 180 114 Q132 110 91 151Z" fill="{hair}"/>'
    elif species == "fox":
        ear_markup = (
            f'<path d="M102 126 L91 20 Q139 38 153 112Z M258 126 L269 20 Q221 38 207 112Z" fill="{skin}" stroke="#6D493E" stroke-opacity=".25" stroke-width="5"/>'
            f'<path d="M111 104 L105 47 Q131 62 140 111Z M249 104 L255 47 Q229 62 220 111Z" fill="{hair}"/>'
        )
        hair_shape = f'<path d="M97 145 Q105 78 180 93 Q255 78 263 145 L237 132 L218 151 L199 132 L180 151 L160 132 L141 151 L122 132Z" fill="{hair}"/>'
        muzzle_markup = '<ellipse cx="180" cy="207" rx="50" ry="29" fill="#FFF1D9"/>'
        nose_markup = '<path d="M170 194 Q180 188 190 194 L180 207Z" fill="#30272A"/>'
        tail_markup = (
            f'<g id="{uid}-tail"><path d="M238 342 Q318 302 326 382 Q330 424 267 413" stroke="{skin}" stroke-width="44" fill="none" stroke-linecap="round"/>'
            f'<path d="M322 383 Q330 424 267 413" stroke="#FFF1D9" stroke-width="34" fill="none" stroke-linecap="round"/></g>'
        )
    elif species == "cat":
        ear_markup = (
            f'<path d="M102 128 L105 31 L164 104Z M258 128 L255 31 L196 104Z" fill="{skin}" stroke="#6D493E" stroke-opacity=".25" stroke-width="5"/>'
            '<path d="M116 100 L119 54 L148 103Z M244 100 L241 54 L212 103Z" fill="#E99A9A"/>'
        )
        muzzle_markup = '<ellipse cx="160" cy="207" rx="25" ry="20" fill="#FFF1E8"/><ellipse cx="200" cy="207" rx="25" ry="20" fill="#FFF1E8"/>'
        nose_markup = '<path d="M171 198 Q180 190 189 198 L180 207Z" fill="#D77F8C"/>'
        whiskers_markup = '<g stroke="#6D493E" stroke-width="4" stroke-linecap="round" opacity=".8"><path d="M132 207 L91 198 M132 218 L91 224 M228 207 L269 198 M228 218 L269 224"/></g>'
        tail_markup = f'<g id="{uid}-tail"><path d="M244 345 Q319 313 320 388 Q319 429 283 435" stroke="{skin}" stroke-width="22" fill="none" stroke-linecap="round"/></g>'
    elif species == "dog":
        ear_markup = (
            f'<path d="M105 111 Q52 67 63 153 Q70 202 119 185 Q137 151 127 119Z" fill="{hair}"/>'
            f'<path d="M255 111 Q308 67 297 153 Q290 202 241 185 Q223 151 233 119Z" fill="{hair}"/>'
        )
        muzzle_markup = '<ellipse cx="180" cy="207" rx="48" ry="31" fill="#F4E5D1"/>'
        nose_markup = '<ellipse cx="180" cy="194" rx="13" ry="9" fill="#30272A"/>'
        tail_markup = f'<g id="{uid}-tail"><path d="M243 345 Q293 333 305 282" stroke="{skin}" stroke-width="25" fill="none" stroke-linecap="round"/></g>'
    elif species == "rabbit":
        ear_markup = (
            f'<ellipse cx="137" cy="69" rx="24" ry="72" transform="rotate(-12 137 69)" fill="{skin}" stroke="#6D493E" stroke-opacity=".2" stroke-width="4"/>'
            f'<ellipse cx="223" cy="69" rx="24" ry="72" transform="rotate(12 223 69)" fill="{skin}" stroke="#6D493E" stroke-opacity=".2" stroke-width="4"/>'
            '<ellipse cx="138" cy="66" rx="10" ry="52" transform="rotate(-12 138 66)" fill="#E99A9A"/>'
            '<ellipse cx="222" cy="66" rx="10" ry="52" transform="rotate(12 222 66)" fill="#E99A9A"/>'
        )
        muzzle_markup = '<ellipse cx="160" cy="207" rx="25" ry="19" fill="#FFF7F1"/><ellipse cx="200" cy="207" rx="25" ry="19" fill="#FFF7F1"/>'
        nose_markup = '<ellipse cx="180" cy="198" rx="9" ry="7" fill="#E98F9B"/>'
        tail_markup = '<g id="' + uid + '-tail"><circle cx="260" cy="365" r="22" fill="#FFF7F1"/></g>'
    elif species == "bear":
        ear_markup = (
            f'<circle cx="112" cy="82" r="37" fill="{skin}" stroke="#6D493E" stroke-opacity=".2" stroke-width="4"/>'
            f'<circle cx="248" cy="82" r="37" fill="{skin}" stroke="#6D493E" stroke-opacity=".2" stroke-width="4"/>'
            '<circle cx="112" cy="82" r="19" fill="#D99B83"/><circle cx="248" cy="82" r="19" fill="#D99B83"/>'
        )
        muzzle_markup = '<ellipse cx="180" cy="207" rx="48" ry="31" fill="#EBC7A7"/>'
        nose_markup = '<ellipse cx="180" cy="194" rx="14" ry="10" fill="#30272A"/>'
        tail_markup = f'<g id="{uid}-tail"><circle cx="258" cy="363" r="15" fill="{skin}"/></g>'
    elif species == "owl":
        ear_markup = (
            f'<path d="M105 115 L94 38 L154 99Z M255 115 L266 38 L206 99Z" fill="{skin}"/>'
            f'<path d="M112 98 L108 61 L139 101Z M248 98 L252 61 L221 101Z" fill="{hair}"/>'
        )
        head_shape = f'<ellipse cx="180" cy="153" rx="96" ry="108" fill="{skin}" stroke="#6D493E" stroke-opacity=".22" stroke-width="5"/>'
        muzzle_markup = '<path d="M165 191 L195 191 L180 219Z" fill="#E9A44A" stroke="#B97732" stroke-width="3"/>'
        nose_markup = ""
        tail_markup = (
            f'<g id="{uid}-tail"><path d="M146 340 L133 387 L165 365Z M180 345 L180 398 L198 364Z M214 340 L227 387 L195 365Z" fill="{hair}"/></g>'
        )
    elif species == "robot":
        ear_markup = '<path d="M180 65 V31" stroke="#687B91" stroke-width="9" stroke-linecap="round"/><circle cx="180" cy="24" r="13" fill="#E5C95A"/>'
        head_shape = f'<rect x="91" y="59" width="178" height="191" rx="35" fill="{skin}" stroke="#64788E" stroke-width="8"/>'
        hair_shape = ""
        muzzle_markup = ""
        nose_markup = '<rect x="172" y="198" width="16" height="12" rx="4" fill="#64788E"/>'
        tail_markup = ""

    brow_markup = (
        f'<path d="M130 155 Q147 142 163 153" stroke="{brow}" stroke-width="7" fill="none" stroke-linecap="round"/>'
        f'<path d="M198 153 Q215 142 231 155" stroke="{brow}" stroke-width="7" fill="none" stroke-linecap="round"/>'
    )
    if species == "owl":
        brow_markup = ""
    eye_markup = (
        f'<ellipse cx="148" cy="178" rx="{eye_r+5}" ry="{eye_r+9}" fill="#FFFFFF"/>'
        f'<ellipse cx="211" cy="178" rx="{eye_r+5}" ry="{eye_r+9}" fill="#FFFFFF"/>'
        f'<circle cx="151" cy="181" r="{eye_r}" fill="#24242B"/>'
        f'<circle cx="214" cy="181" r="{eye_r}" fill="#24242B"/>'
        '<circle cx="154" cy="177" r="4" fill="#FFFFFF"/>'
        '<circle cx="217" cy="177" r="4" fill="#FFFFFF"/>'
    )
    return f"""
<svg id="{uid}" class="character-svg" data-species="{species}" viewBox="0 0 360 520" role="img" aria-label="{_text(character.get('name'), 40)}">
  <ellipse cx="180" cy="488" rx="100" ry="19" fill="#1D2630" opacity=".18"/>
  <g id="{uid}-body">
    {tail_markup}
    <g id="{uid}-legs" stroke-linecap="round" stroke-linejoin="round">
      <path d="M145 354 Q142 412 132 452" stroke="{pants}" stroke-width="37" fill="none"/>
      <path d="M214 354 Q218 412 230 452" stroke="{pants}" stroke-width="37" fill="none"/>
      <path d="M130 452 Q110 464 112 480 L163 480 Q174 465 151 452Z" fill="{shoe}"/>
      <path d="M226 452 Q210 464 220 480 L271 480 Q279 465 248 452Z" fill="{shoe}"/>
    </g>
    <g id="{uid}-arms" stroke-linecap="round" stroke-linejoin="round">
      <path id="{uid}-arm-left" d="M123 264 Q82 293 76 354" stroke="{skin}" stroke-width="28" fill="none"/>
      <circle cx="76" cy="355" r="17" fill="{skin}"/>
      <g id="{uid}-arm-right">
        <path d="M238 264 Q279 291 285 348" stroke="{skin}" stroke-width="28" fill="none"/>
        <circle cx="285" cy="349" r="17" fill="{skin}"/>
      </g>
    </g>
    <path d="M125 244 Q180 222 235 244 L251 354 Q180 385 109 354Z" fill="{shirt}" stroke="#FFFFFF" stroke-opacity=".18" stroke-width="5"/>
    <path d="M153 244 Q180 266 207 244" fill="none" stroke="#FFFFFF" stroke-opacity=".4" stroke-width="7"/>
    <g id="{uid}-head">
      {ear_markup}
      {head_shape}
      {hair_shape}
      {muzzle_markup}
      {brow_markup}
      {eye_markup}
      {nose_markup}
      {whiskers_markup}
      {mouth}
      <ellipse cx="116" cy="205" rx="13" ry="7" fill="#E88786" opacity=".35"/>
      <ellipse cx="244" cy="205" rx="13" ry="7" fill="#E88786" opacity=".35"/>
    </g>
  </g>
</svg>
"""


def build_cartoon_project(
    project: dict[str, Any],
    storyboard: dict[str, Any],
    audio_assets: list[dict[str, Any]],
) -> dict[str, str]:
    duration = int(project["duration_seconds"])
    ratio = str(project.get("aspect_ratio") or "9:16")
    width, height, resolution = RATIOS.get(ratio, RATIOS["9:16"])
    style = str(project.get("style") or "2d-cartoon")
    language = str(project.get("language") or "auto").lower()
    html_language = "ur" if language == "ur" else "hi" if language in {"hi", "hinglish"} else language if language in {"en", "mr"} else "en"
    html_direction = "rtl" if language == "ur" else "ltr"
    characters = storyboard.get("characters") if isinstance(storyboard.get("characters"), list) else []
    scenes = storyboard.get("scenes") if isinstance(storyboard.get("scenes"), list) else []
    char_map = {str(item.get("id")): item for item in characters if isinstance(item, dict)}
    if not scenes:
        raise ValueError("The cartoon storyboard has no scenes.")

    slot = duration / len(scenes)
    audio_map = {str(item.get("scene_id")): item for item in audio_assets}
    scene_hosts: list[str] = []
    audio_markup: list[str] = []
    files: dict[str, str] = {}

    if ratio == "9:16":
        title_size, caption_size = 54, 30
    elif ratio == "16:9":
        title_size, caption_size = 52, 30
    else:
        title_size, caption_size = 48, 30

    for index, scene in enumerate(scenes):
        scene_id = _id(scene.get("id"), f"scene-{index+1}")
        scene_start = round(index * slot, 3)
        scene_duration = round(slot, 3)
        environment = _id(scene.get("environment"), "forest")
        title = _text(scene.get("scene_title") or storyboard.get("title"), 72)
        action = _text(scene.get("action"), 120)
        expression = str(scene.get("expression") or "happy").lower()
        if expression not in {"happy", "sad", "surprised", "angry", "curious", "neutral", "scared"}:
            expression = "happy"
        motion = str(scene.get("motion") or "idle").lower()
        if motion not in {"idle", "walk", "run", "jump", "wave", "point", "look"}:
            motion = "idle"
        camera = str(scene.get("camera_move") or "push-in").lower()
        if camera not in {"push-in", "pan-left", "pan-right", "zoom-out", "static"}:
            camera = "push-in"

        char_ids = scene.get("character_ids") if isinstance(scene.get("character_ids"), list) else []
        speaker_id = str(
            scene.get("speaker_id")
            or (char_ids[0] if char_ids else (characters[0].get("id") if characters else ""))
        )
        if speaker_id and speaker_id not in char_ids:
            char_ids = [speaker_id] + char_ids
        char_ids = [str(value) for value in char_ids if str(value) in char_map][:3]
        if not char_ids and characters:
            char_ids = [str(characters[0].get("id"))]
            speaker_id = char_ids[0]

        if ratio == "16:9":
            positions = {1: [41], 2: [24, 60], 3: [8, 42, 76]}.get(len(char_ids), [41])
            width_pct = {1: 18, 2: 16, 3: 14}.get(len(char_ids), 18)
            character_height, character_bottom = 54, 40
            dialogue_class = "landscape"
        elif ratio == "1:1":
            positions = {1: [32], 2: [15, 55], 3: [3, 39, 75]}.get(len(char_ids), [32])
            width_pct = {1: 36, 2: 30, 3: 24}.get(len(char_ids), 36)
            character_height, character_bottom = 42, 40
            dialogue_class = "square"
        else:
            positions = {1: [28], 2: [3, 57], 3: [0, 34, 68]}.get(len(char_ids), [28])
            width_pct = {1: 48, 2: 40, 3: 32}.get(len(char_ids), 48)
            character_height, character_bottom = 35, 40
            dialogue_class = "portrait"

        timeline_js: list[str] = []
        char_markup: list[str] = []
        audio_info = audio_map.get(scene_id, {})
        audio_duration = float(audio_info.get("duration") or 0)
        animation_filename = str(audio_info.get("animation_filename") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", animation_filename):
            animation_filename = ""
        animation_markup = (
            f'<video id="{scene_id}-animation" class="clip scene-animation" data-start="0" '
            f'data-duration="{scene_duration}" data-track-index="0" data-track-kind="video" '
            f'src="assets/animation/{animation_filename}" muted playsinline></video>'
            if animation_filename else ""
        )
        speech_start = round(float(audio_info.get("speech_start_seconds") if audio_info.get("speech_start_seconds") is not None else min(1.05, slot * .16)), 3)
        speech_duration = min(
            audio_duration or max(1.5, slot * .5),
            max(1.2, slot - 1.25),
        )
        caption_words = audio_info.get("words") if isinstance(audio_info.get("words"), list) else []
        if index == 0 and isinstance(project.get("narration_words"), list):
            caption_words = sorted(
                [*project["narration_words"], *caption_words],
                key=lambda word: float(word.get("start_seconds") or 0) if isinstance(word, dict) else 0.0,
            )
        caption_markup, caption_timeline = build_karaoke_caption_markup(
            caption_words,
            overlay_id=scene_id,
            rtl=language == "ur",
            bottom_percent=30 if ratio == "9:16" else 18,
        )
        if caption_timeline:
            timeline_js.append(caption_timeline)

        for char_index, char_id in enumerate(char_ids if not animation_filename else []):
            character = char_map[char_id]
            uid = f"char-{index+1}-{_id(char_id, 'hero')}"
            left_pct = positions[char_index]
            char_markup.append(
                f'<div class="character-slot" id="{uid}-slot" '
                f'style="left:{left_pct}%;width:{width_pct}%;height:{character_height}%;bottom:{character_bottom}%;">'
                f'{_character_svg(character, uid, expression if char_id == speaker_id else "neutral", style)}</div>'
            )
            timeline_js.append(
                f'const body{index}_{char_index} = "#{uid}-body";'
                f'tl.fromTo(body{index}_{char_index}, {{y:14}}, {{y:0,duration:.45,ease:"back.out(1.6)"}}, .25);'
                f'tl.to(body{index}_{char_index}, {{y:-8,duration:.28,ease:"power2.out"}}, {1.25 + char_index*.16});'
                f'tl.to(body{index}_{char_index}, {{y:0,duration:.34,ease:"power2.inOut"}}, {1.53 + char_index*.16});'
            )
            if character.get("species") in {"fox", "cat", "dog", "rabbit", "bear", "owl"}:
                timeline_js.append(
                    f'tl.to("#{uid}-tail", {{rotation:6,duration:.35,repeat:3,yoyo:true,ease:"sine.inOut",transformOrigin:"20% 80%"}}, .55);'
                )
            if char_id == speaker_id:
                mouth_id = f"#{uid}-mouth"
                lip_envelope = audio_info.get("lip_envelope") if isinstance(audio_info.get("lip_envelope"), list) else []
                for sample_index, sample in enumerate(lip_envelope):
                    level = max(0.0, min(1.0, float(sample or 0)))
                    scale = .55 + level * 1.35
                    sample_time = speech_start + sample_index / 60.0
                    timeline_js.append(
                        f'tl.set("{mouth_id}", {{scaleY:{scale:.3f},transformOrigin:"50% 50%"}}, {sample_time:.4f});'
                    )
                if lip_envelope:
                    close_time = speech_start + len(lip_envelope) / 60.0
                    timeline_js.append(
                        f'tl.set("{mouth_id}", {{scaleY:.55,transformOrigin:"50% 50%"}}, {close_time:.4f});'
                    )
                if motion == "wave":
                    timeline_js.append(
                        f'tl.to("#{uid}-arm-right", {{x:10,y:-16,duration:.25,ease:"power2.out"}}, 1.0);'
                        f'tl.to("#{uid}-arm-right", {{x:-4,y:-5,duration:.22,repeat:2,yoyo:true,ease:"sine.inOut"}}, 1.25);'
                        f'tl.to("#{uid}-arm-right", {{x:0,y:0,duration:.2}}, 2.1);'
                    )
                elif motion == "jump":
                    timeline_js.append(
                        f'tl.to(body{index}_{char_index}, {{y:-54,duration:.28,ease:"power2.out"}}, 1.0);'
                        f'tl.to(body{index}_{char_index}, {{y:0,duration:.38,ease:"bounce.out"}}, 1.28);'
                    )
                elif motion == "run":
                    timeline_js.append(
                        f'tl.to("#{uid}-slot", {{x:{width*.06},duration:.6,ease:"power2.inOut"}}, 1.0);'
                    )

        dialogue = _text(scene.get("dialogue"), 140)
        speaker = _text(char_map.get(speaker_id, {}).get("name") or "Character", 40)
        dialogue_hold = max(3.3, audio_duration + .65)
        dialogue_end = min(scene_duration - .18, speech_start + dialogue_hold)
        if animation_filename:
            camera_anim = ""
        elif camera == "push-in":
            camera_anim = (
                f'tl.fromTo("#{scene_id}-inner", {{scale:1.04}}, '
                f'{{scale:1,duration:{scene_duration},ease:"none"}}, 0);'
            )
        elif camera == "zoom-out":
            camera_anim = (
                f'tl.fromTo("#{scene_id}-inner", {{scale:1.12}}, '
                f'{{scale:1,duration:{scene_duration},ease:"none"}}, 0);'
            )
        elif camera in {"pan-left", "pan-right"}:
            x0, x1 = (24, -24) if camera == "pan-left" else (-24, 24)
            camera_anim = (
                f'tl.fromTo("#{scene_id}-inner", {{x:{x0}}}, '
                f'{{x:{x1},duration:{scene_duration},ease:"none"}}, 0);'
            )
        else:
            camera_anim = ""
        timeline_js.append(camera_anim)

        bg = _background_svg(environment, width, height, index + 1)
        scene_markup = (
            f'<div id="{scene_id}-inner" class="scene-inner" data-layout-allow-overflow="true">{bg}{animation_markup}'
            f'{"".join(char_markup)}'
            f'{caption_markup}'
            f'</div>'
        )
        scene_hosts.append(
            f'<div id="{scene_id}" class="clip" data-composition-id="{scene_id}" '
            f'data-composition-src="compositions/{scene_id}.html" data-start="{scene_start}" '
            f'data-duration="{scene_duration}" data-track-index="1" data-track-kind="graphics" '
            f'data-width="{width}" data-height="{height}"></div>'
        )

        scene_html = f"""<template>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:"Noto Sans","Liberation Sans",Arial,sans-serif}}
#root{{position:absolute;inset:0;width:100%;height:100%;overflow:hidden;background:#172a37}}
.scene-inner{{position:absolute;inset:0;overflow:hidden}}
.scene-bg{{position:absolute;inset:0;width:100%;height:100%}}
.scene-animation{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1}}
.scene-heading{{position:absolute;z-index:3;top:16%;left:6%;right:6%;padding:10px 16px;border-radius:14px;text-align:left;color:#fff;background:rgba(13,25,36,.42);box-shadow:none;text-shadow:0 2px 8px rgba(0,0,0,.24);max-width:68%}}
.scene-heading h1{{font-size:{max(28, title_size//2)}px;line-height:1.08;font-weight:900;letter-spacing:-.5px;text-wrap:balance}}
.scene-heading p{{font-size:30px;line-height:1.25;margin:6px 0 0;max-width:100%;font-weight:650;opacity:.86}}
.character-slot{{position:absolute;z-index:4;display:flex;align-items:flex-end;justify-content:center;transform-origin:50% 100%}}
.character-svg{{width:100%;height:100%;overflow:visible;filter:drop-shadow(0 15px 15px rgba(20,36,45,.13))}}
.dialogue-box{{position:absolute;z-index:7;left:24%;right:24%;bottom:38%;padding:16px 18px 18px;border-radius:24px;background:rgba(255,255,255,.97);box-shadow:0 12px 32px rgba(24,37,49,.18);text-align:center;opacity:0}}
.dialogue-box.landscape{{bottom:34%}}
.dialogue-box.square{{bottom:36%}}
.dialogue-box span{{display:block;color:#205c3d;font-size:30px;line-height:1.15;font-weight:900;letter-spacing:.5px;text-transform:uppercase;margin-bottom:9px}}
.dialogue-box p{{display:block;width:100%;max-width:100%;font-size:{caption_size}px;line-height:1.2;font-weight:900;color:#182b31;white-space:normal!important;word-break:normal;overflow-wrap:anywhere;text-wrap:balance}}
</style>
<div id="root" data-composition-id="{scene_id}" data-duration="{scene_duration}" data-width="{width}" data-height="{height}">
{scene_markup}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
{"".join(timeline_js)}
window.__timelines["{scene_id}"] = tl;
tl.seek(0);
</script>
</template>
"""
        files[f"compositions/{scene_id}.html"] = scene_html

        if audio_info.get("filename") and audio_duration > 0:
            audio_start = round(scene_start + speech_start, 3)
            audio_track_duration = round(min(audio_duration, max(.1, slot - 1.0)), 3)
            audio_name = _text(audio_info["filename"], 80)
            audio_markup.append(
                f'<audio id="dialogue-{scene_id}" class="clip" data-start="{audio_start}" '
                f'data-duration="{audio_track_duration}" data-track-index="20" data-track-kind="audio" '
                f'data-volume="1" data-fade-in="0.040" data-fade-out="0.120" '
                f'src="assets/audio/{audio_name}"></audio>'
            )

    extra_tracks = project.get("audio_tracks") if isinstance(project.get("audio_tracks"), list) else []
    track_indexes = {"narration": 10, "dialogue": 20, "music": 40, "foley": 50}
    for track_number, track in enumerate(extra_tracks):
        if not isinstance(track, dict):
            continue
        filename = str(track.get("filename") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", filename):
            continue
        try:
            start = max(0.0, float(track.get("start_seconds") or 0))
            track_duration = max(0.05, float(track.get("duration_seconds") or 0))
            volume = min(1.5, max(0.0, float(track.get("volume", 1.0))))
            fade_in = min(5.0, max(0.0, float(track.get("fade_in_seconds") or 0)))
            fade_out = min(5.0, max(0.0, float(track.get("fade_out_seconds") or 0)))
        except (TypeError, ValueError):
            continue
        if start >= duration:
            continue
        track_duration = min(track_duration, duration - start)
        kind = str(track.get("track") or "foley").lower()
        track_index = track_indexes.get(kind, 50)
        audio_markup.append(
            f'<audio id="audio-extra-{track_number + 1}" class="clip" data-start="{start:.4f}" '
            f'data-duration="{track_duration:.4f}" data-track-index="{track_index}" '
            f'data-track-kind="audio" data-volume="{volume:.3f}" '
            f'data-fade-in="{fade_in:.3f}" data-fade-out="{fade_out:.3f}" '
            f'src="assets/audio/{filename}"></audio>'
        )

    root_html = f"""<!doctype html>
<html lang="{html_language}" dir="{html_direction}" data-resolution="{resolution}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width={width},height={height}"/>
<title>{_text(storyboard.get("title") or "ClipKaro Cartoon", 80)}</title>
<script src="assets/gsap.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:"Noto Sans","Liberation Sans",Arial,sans-serif}}
html,body{{width:{width}px;height:{height}px;overflow:hidden;background:#172a37}}
#root{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:#172a37}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}">
{"".join(scene_hosts)}
{"".join(audio_markup)}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
window.__timelines["main"] = tl;
tl.seek(0);
</script>
</body>
</html>
"""
    files["index.html"] = root_html
    return files


def build_cartoon_html(
    project: dict[str, Any],
    storyboard: dict[str, Any],
    audio_assets: list[dict[str, Any]],
) -> str:
    return build_cartoon_project(project, storyboard, audio_assets)["index.html"]

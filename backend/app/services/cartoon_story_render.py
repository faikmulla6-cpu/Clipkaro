"""Compile validated director data and measured speech assets into HyperFrames."""
from __future__ import annotations

import copy
import html
import json
import re
from .cartoon_story import RATIOS, StoryValidationError, normalize_director_story, resolve_cartoon_language
from .cartoon_timing import SPEECH_LINE_CAPTION_SOURCE, normalize_word_boundaries, build_karaoke_caption_markup
from .roman_hindi import DEVANAGARI, romanize_hindi


def _roman_spelling_key(value: str) -> str:
    letters = re.sub(r"[^a-z0-9]", "", value.casefold())
    letters = letters.replace("ee", "i").replace("oo", "u")
    letters = re.sub(r"([a-z])\1+", r"\1", letters)
    letters = re.sub(r"n(?=[bp])", "m", letters)
    # ASR and transliteration often retain a silent vowel or spell the same
    # Hindi word differently from a person's Roman script.
    return {
        "apaki": "apki", "cand": "chand", "kahati": "kehti",
        "rakhati": "rakhti", "toh": "to",
    }.get(letters, letters)


def _roman_caption_words(words: list[dict], line: str) -> list[dict]:
    texts = [word["text"] for word in words]
    roman = [romanize_hindi(value.replace("।", ".").replace("॥", "."))
             if DEVANAGARI.search(value) else value.replace("|", ".") for value in texts]
    scripted = line.split()

    # Restore the authored spelling only if each token agrees with the timed speech.
    scripted_keys = [_roman_spelling_key(value) for value in scripted]
    if (all(char.isascii() or not char.isalpha() for char in line)
            and all(scripted_keys) and scripted_keys == [_roman_spelling_key(value) for value in roman]):
        roman = scripted
    return [{**word, "text": value} for word, value in zip(words, roman)]


def schedule_speech(
    story: dict, audio_assets: list[dict], *, language: str = "auto"
) -> tuple[dict, list[dict], list[dict]]:
    result = copy.deepcopy(story)
    lookup = {a["id"]: a for a in audio_assets}
    tracks, words = [], []
    for scene in result["scenes"]:
        measured, audio = [], []
        for line in sorted(scene["speech"], key=lambda s:s["start"]):
            asset = lookup.get(line["id"])
            if not asset:
                raise StoryValidationError("A planned narration or dialogue line has no audio asset.")
            filename = str(asset.get("filename") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.(mp3|wav|m4a)", filename):
                raise StoryValidationError("Speech asset filename is invalid.")
            duration = float(asset["duration"])
            if not 0 < duration < 120:
                raise StoryValidationError("Speech duration must come from a valid audio probe.")
            measured.append((line, asset, filename, duration))

        # Reserve space for every later line before following the model's preferred starts.
        # This recovers late cues without dropping words or changing the speaker order.
        latest_end = scene["duration"] - .05
        latest_starts = []
        for _, _, _, duration in reversed(measured):
            latest_start = latest_end - duration
            latest_starts.append(latest_start)
            latest_end = latest_start - .2
        if latest_starts and latest_starts[-1] < -1e-9:
            raise StoryValidationError("The recorded speech does not fit its scene. Choose a longer video or use fewer spoken words.")
        cursor = 0.0
        for (line, asset, filename, duration), latest_start in zip(measured, reversed(latest_starts)):
            start = max(cursor, min(line["start"], latest_start))
            boundaries = asset.get("word_boundaries") or []
            local_words = []
            timing_source = asset.get("timing_source", "tts_word_boundary")
            if boundaries:
                local_words = normalize_word_boundaries(boundaries,audio_duration=duration,global_start=start,speaker_id=line["speaker_id"],track=line["track"])
                if not local_words:
                    raise StoryValidationError("Speech word timestamps are empty or outside the measured audio.")
                caption_words = _roman_caption_words(local_words, line["text"]) if language == "hinglish" else local_words
            else:
                window = asset.get("caption_window")
                if timing_source != SPEECH_LINE_CAPTION_SOURCE or not window or not 0 <= window[0] < window[1] <= duration:
                    raise StoryValidationError("Speech requires word timestamps or a detected speech window for captions.")
                text = line["text"]
                if language == "hinglish" and DEVANAGARI.search(text):
                    text = romanize_hindi(text)
                caption_words = [{
                    "text": text, "speaker_id": line["speaker_id"], "track": line["track"],
                    "start_seconds": start + window[0], "end_seconds": start + window[1],
                }]
            global_words = [{**w,"start_seconds":round(w["start_seconds"]+scene["start"],4),"end_seconds":round(w["end_seconds"]+scene["start"],4),
                             "source":timing_source} for w in caption_words]
            words.extend(global_words)
            audio.append({"line_id":line["id"],"start":start,"duration":duration,"speaker_id":line["speaker_id"],"track":line["track"],"words":local_words,"envelope":asset.get("lip_envelope") or []})
            tracks.append({"track":line["track"],"filename":filename,"start_seconds":scene["start"]+start,"duration_seconds":duration,
                           "volume":1,"fade_in_seconds":.025,"fade_out_seconds":.06})
            cursor=start+duration+.2
        scene["audio"]=audio
    return result, tracks, sorted(words,key=lambda w:w["start_seconds"])


def caption_timeline(story: dict, *, language: str) -> list[dict]:
    """Expose each recorded line and its placement in the finished cartoon."""
    captions = []
    people = {item["id"]: item["name"] for item in story["characters"]}
    for scene in story["scenes"]:
        lines = {line["id"]: line for line in scene["speech"]}
        for cue in scene["audio"]:
            line = lines[cue["line_id"]]
            text = " ".join(line["text"].split())
            if language == "hinglish" and DEVANAGARI.search(text):
                text = romanize_hindi(text)
            start = scene["start"] + cue["start"]
            captions.append({
                "id": line["id"],
                "speaker": "Narrator" if line["track"] == "narration" else people[line["speaker_id"]],
                "text": text,
                "start_seconds": round(start, 4),
                "end_seconds": round(start + cue["duration"], 4),
            })
    return captions


def saved_caption_timeline(story: dict, assets: dict, *, duration: int, language: str) -> list[dict] | None:
    """Reconstruct timing for completed V3 projects made before caption timelines were saved."""
    if story.get("schema_version") != 3:
        return None
    try:
        normalized = normalize_director_story(story, duration=duration)
        clips = []
        for scene in normalized["scenes"]:
            for line in scene["speech"]:
                line_id = line["id"]
                seconds = float(assets[line_id]["duration"])
                clips.append({
                    "id": line_id, "filename": line_id + ".mp3", "duration": seconds,
                    "timing_source": SPEECH_LINE_CAPTION_SOURCE, "caption_window": (0, seconds),
                })
        scheduled, _, _ = schedule_speech(normalized, clips, language=language)
        return caption_timeline(scheduled, language=language)
    except (StoryValidationError, KeyError, TypeError, ValueError):
        return None


def build_story_project(project: dict, storyboard: dict, audio_assets: list[dict]) -> dict[str,str]:
    duration=int(project["duration_seconds"])
    story=normalize_director_story(storyboard,duration=duration)
    for c in story["characters"]:
        original=next(x for x in storyboard["characters"] if x["id"]==c["id"])
        c["voice_id"]=original.get("voice_id","")
    story_language = resolve_cartoon_language(project.get("language") or "auto", project.get("prompt") or "")
    story,tracks,words=schedule_speech(story,audio_assets,language=story_language)
    ratio=project.get("aspect_ratio","9:16")
    if ratio not in RATIOS:
        raise StoryValidationError("Unsupported aspect ratio.")
    w,h,_=RATIOS[ratio]
    caption_on=bool(project.get("captions_enabled",True))
    rtl=story_language=="ur"
    caption_html,caption_js=build_karaoke_caption_markup(words,overlay_id="story",rtl=rtl,bottom_percent=9,strict_timing=True) if caption_on else ("","")
    extras=project.get("audio_tracks") or []
    audios=[]
    for i,track in enumerate([*tracks,*extras]):
        filename=str(track.get("filename") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",filename) or filename in {".",".."}:
            raise StoryValidationError("Audio filenames must be local project assets.")
        at=float(track.get("start_seconds",0));length=float(track["duration_seconds"])
        if not 0<=at<duration or not 0<length<=duration-at+.001:
            raise StoryValidationError("Audio track falls outside the video.")
        volume=float(track.get("volume",1))
        if not 0<=volume<=1.5:
            raise StoryValidationError("Audio gain is invalid.")
        lane={"narration":10,"dialogue":20,"music":30,"ambience":40,"foley":50,"sfx":50}.get(track["track"],50)
        audios.append(f'<audio id="story-audio-{i}" class="clip" data-start="{at:.4f}" data-duration="{length:.4f}" data-track-index="{lane}" data-volume="{volume:.3f}" data-fade-in="{float(track.get("fade_in_seconds",.03)):.3f}" data-fade-out="{float(track.get("fade_out_seconds",.1)):.3f}" src="assets/audio/{filename}"></audio>')
    payload=json.dumps({"kind":"story-v3","story":story,"width":w,"height":h,"duration":duration},ensure_ascii=True,allow_nan=False).replace("<","\\u003c")
    size=round(min(w,h)*.043)
    direction="rtl" if rtl else "ltr"
    language={"hinglish":"hi-Latn","auto":"en"}.get(story_language,story_language)
    root=f"""<!doctype html><html lang="{html.escape(language,quote=True)}" dir="{direction}">
<head><meta charset="UTF-8"><meta name="viewport" content="width={w},height={h}"><title>{html.escape(story['title'])}</title>
<script src="assets/gsap.min.js"></script><script src="assets/animation.js"></script>
<style>*{{box-sizing:border-box;margin:0}}html,body,#root{{width:{w}px;height:{h}px;overflow:hidden;background:#172C3E}}#root{{position:relative}}
#story-frame{{position:absolute;inset:0}}.caption-phrase{{position:absolute;left:10%;right:10%;bottom:9%;color:#fff;background:rgba(8,18,31,.86);padding:12px 22px;border-radius:12px;font-size:{size}px;font-family:"Noto Sans";font-weight:700;line-height:1.5;text-align:center;direction:{direction};unicode-bidi:plaintext;z-index:10}}.caption-word{{display:inline;white-space:normal}}</style>
</head><body><div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{w}" data-height="{h}" data-fps="30">
<div id="story-frame" class="clip" data-start="0" data-duration="{duration}" data-track-index="0" data-layout-allow-overflow="true"></div>
{caption_html}{''.join(audios)}</div><script>
window.__timelines=window.__timelines||{{}};
const draw=ClipKaroAnimation.createFrameRenderer(document.getElementById("story-frame"),{payload});
let previous=0;const clock={{get time(){{return previous}},set time(t){{previous=t;draw(t)}}}};
const tl=gsap.timeline({{paused:true}});tl.to(clock,{{time:{duration},duration:{duration},ease:"none"}},0);
{caption_js}
draw(0);window.__timelines.main=tl;
</script></body></html>"""
    timeline = {
        "tracks": [*tracks, *extras],
        "words": [item for item in words if item["source"] != SPEECH_LINE_CAPTION_SOURCE],
        "caption_lines": [item for item in words if item["source"] == SPEECH_LINE_CAPTION_SOURCE],
    }
    return {"index.html":root,"storyboard.json":json.dumps(story,ensure_ascii=False,indent=2),
            "audio-timeline.json":json.dumps(timeline,ensure_ascii=False,indent=2),
            "hyperframes.json":json.dumps({"paths":{"blocks":"compositions","assets":"assets"},"media":{"autoProxy":True}}),
            "meta.json":json.dumps({"id":str(project.get("id") or "story-v3"),"name":story["title"],"engine_version":"story-v3"})}

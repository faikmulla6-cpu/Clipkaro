from __future__ import annotations

import html
import json
import re
from typing import Any

from app.services.cartoon_renderer import RATIOS
from app.services.cartoon_timing import group_caption_phrases


def _safe_filename(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    if "/" in raw or "\\" in raw:
        return fallback
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", raw):
        return fallback
    return raw


def _caption_markup(words: list[dict[str, Any]], *, rtl: bool) -> str:
    phrases = group_caption_phrases(words)
    direction = "rtl" if rtl else "ltr"
    output = []
    for index, phrase in enumerate(phrases):
        if not phrase:
            continue
        start = min(float(item["start_seconds"]) for item in phrase)
        end = max(float(item["end_seconds"]) for item in phrase)
        text = " ".join(html.escape(str(item.get("text") or ""), quote=True) for item in phrase)
        output.append(
            f'<div id="caption-{index + 1}" class="clip caption-phrase" dir="{direction}" '
            f'data-start="{start:.4f}" data-duration="{max(0.05, end - start):.4f}" '
            f'data-track-index="30" data-layout-ignore>{text}</div>'
        )
    return "".join(output)


def build_final_hyperframes_project(
    *,
    project_id: str,
    title: str,
    duration_seconds: int,
    aspect_ratio: str,
    animation_filename: str,
    audio_tracks: list[dict[str, Any]],
    caption_words: list[dict[str, Any]],
    language: str = "auto",
) -> dict[str, str]:
    """Create a HyperFrames final-mix project from a Remotion animation and timed audio."""
    width, height, resolution = RATIOS.get(aspect_ratio, RATIOS["9:16"])
    language = str(language or "auto").lower()
    rtl = language in {"ur", "ar", "fa"}
    html_language = "ur" if language == "ur" else "hi" if language in {"hi", "hinglish"} else language if language in {"en", "mr"} else "en"
    animation_filename = _safe_filename(animation_filename, "animation.mp4")

    audio_markup = []
    for index, track in enumerate(audio_tracks):
        if not isinstance(track, dict):
            continue
        filename = _safe_filename(track.get("filename"), "")
        if not filename:
            continue
        try:
            start = max(0.0, float(track.get("start_seconds") or 0))
            track_duration = max(0.05, float(track.get("duration_seconds") or 0))
            volume = min(1.5, max(0.0, float(track.get("volume", 1.0))))
        except (TypeError, ValueError):
            continue
        if start >= duration_seconds:
            continue
        track_duration = min(track_duration, duration_seconds - start)
        kind = str(track.get("track") or "dialogue").lower()
        track_index = {"narration": 10, "dialogue": 20, "music": 40, "foley": 50}.get(kind, 25)
        audio_markup.append(
            f'<audio id="audio-{index + 1}" class="clip" data-start="{start:.4f}" '
            f'data-duration="{track_duration:.4f}" data-track-index="{track_index}" '
            f'data-track-kind="audio" data-volume="{volume:.3f}" '
            f'src="assets/audio/{filename}"></audio>'
        )

    captions = _caption_markup(caption_words, rtl=rtl)
    direction = "rtl" if rtl else "ltr"
    root_html = f"""<!doctype html>
<html lang="{html_language}" dir="{direction}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width={width},height={height}"/>
<title>{html.escape(str(title or "ClipKaro Cartoon"), quote=True)}</title>
<script src="assets/gsap.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{width}px;height:{height}px;overflow:hidden;background:#0e1823}}
#root{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:#0e1823}}
#animation{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
.caption-phrase{{position:absolute;left:7%;right:7%;bottom:{36 if aspect_ratio == "9:16" else 12}%;z-index:90;
padding:16px 24px;border-radius:18px;background:rgba(5,10,18,.78);
color:#fff;font-family:"Noto Sans",sans-serif;
font-size:{48 if aspect_ratio == "16:9" else 54}px;font-weight:800;line-height:1.5;
text-align:center;text-shadow:0 2px 5px rgba(0,0,0,.9);unicode-bidi:plaintext;direction:{direction}}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration_seconds}"
 data-width="{width}" data-height="{height}">
<video id="animation" class="clip" data-start="0" data-duration="{duration_seconds}"
 data-track-index="0" data-track-kind="video" src="assets/{animation_filename}" muted playsinline></video>
{"".join(audio_markup)}
{captions}
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
    return {
        "index.html": root_html,
        "hyperframes.json": json.dumps({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
            "media": {"autoProxy": True},
        }, indent=2),
        "meta.json": json.dumps({"id": project_id, "name": str(title or "ClipKaro Cartoon")}, indent=2),
    }

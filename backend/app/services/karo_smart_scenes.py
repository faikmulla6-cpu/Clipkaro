"""Scene-aware Smart Layout planning and safe per-shot portrait composition.

The source may alternate wide two-person camera angles with solo close-ups.
Never reuse a two-person crop from a different camera shot. A genuine Dual
Stack is used only when both faces coexist IN THE SAME SCENE. Otherwise render
one real face, or fit the uncropped source against a subtle blurred backing.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("clipkaro.smart_layouts.scenes")

MAX_SEGMENTS = 24
SAMPLE_INTERVAL = .4


@dataclass(frozen=True)
class Scene:
    start: float
    end: float
    mode: str
    centers: tuple[tuple[float, float], ...] = ()
    switches: tuple[tuple[float, int], ...] = ()


def scene_boundaries(visuals: list, pairs: list, singles: list) -> list[int]:
    """Create shot boundaries from large visual jumps (not mouth motion).

    Small moving faces and subtitles do not create a scene. A camera cut
    normally changes the spatial thumbnail and face geometry together.
    """
    import numpy as np
    n = len(visuals)
    boundaries = [0]
    for i in range(1, n):
        before, after = visuals[i-1], visuals[i]
        if before is None or after is None:
            continue
        jump = float(np.mean(np.abs(after.astype("float32") - before.astype("float32"))))
        pair_flip = bool(pairs[i-1]) != bool(pairs[i])
        a, b = singles[i-1], singles[i]
        location_jump = bool(a and b and abs(a[0] - b[0]) > .25)
        # A hard edit is more than an ordinary head movement. Prevent one
        # accidental detection or lighting flicker from creating tiny scenes.
        is_cut = jump > .27 or (jump > .18 and (pair_flip or location_jump))
        if is_cut and i - boundaries[-1] >= 2:
            boundaries.append(i)
    if len(boundaries) > 1 and n - boundaries[-1] < 2:
        boundaries.pop()
    return boundaries


def _single_face(found) -> tuple[float, float, float, float] | None:
    significant = [f for f in found if f[2] >= .042 and f[3] >= .06]
    if not significant:
        return None
    return max(significant, key=lambda f: f[2] * f[3])


def _decisions_for_scene(
    start_i: int, end_i: int, pairs: list, singles: list,
    scores: list, energy: list, requested: str,
    start_seconds: float, end_seconds: float,
    window: float,
) -> Scene:
    import numpy as np
    from .karo_smart_layouts import _normalize_activity, smooth_turns
    count = max(1, end_i - start_i)
    matched = [p for p in pairs[start_i:end_i] if p is not None]
    available = [f for f in singles[start_i:end_i] if f is not None]
    # One person taking a close-up must never be duplicated into split panels.
    if len(matched) >= max(3, math.ceil(count * .55)):
        first = tuple(float(np.median([p[0][k] for p in matched])) for k in (0, 1))
        second = tuple(float(np.median([p[1][k] for p in matched])) for k in (0, 1))
        if second[0] - first[0] >= .16:
            activity = _normalize_activity(scores[start_i:end_i])
            votes = []
            for k, n in enumerate(range(start_i, end_i)):
                if pairs[n] is None or energy[n] < .18:
                    votes.append(None)
                    continue
                a, b = float(activity[k][0]), float(activity[k][1])
                if a + b < .3 or abs(a - b) / max(a + b, .0001) < .22:
                    votes.append(None)
                else:
                    votes.append(0 if a > b else 1)
            turns = smooth_turns(votes, window)
            changes = tuple((t, who) for t, who in turns)
            confident = sum(v is not None for v in votes)
            groups = [votes.count(0), votes.count(1)]
            conversational = confident >= max(3, count * .12) and min(groups) >= max(2, confident * .18)
            if requested == "dual_stack":
                mode = "dual_stack"
            elif requested == "auto":
                mode = "dual_stack" if conversational else "speaker_focus"
            else:
                mode = "speaker_focus"
            return Scene(start_seconds, end_seconds, mode, (first, second), changes)
    if len(available) >= max(2, math.ceil(count * .22)):
        # Face position in a close-up is independent of the last wide shot.
        face = tuple(float(np.median([f[k] for f in available])) for k in (0, 1))
        return Scene(start_seconds, end_seconds, "single", (face,))
    return Scene(start_seconds, end_seconds, "wide")


def analyze_scenes(source: Path, start: float, duration: float, mode: str, ffmpeg: str):
    """Bounded per-scene face samples, without remote model/API calls."""
    import cv2
    import numpy as np
    from .karo_smart_layouts import LayoutPlan, _audio_energy, _pair

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return None
    try:
        w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w < 240 or h < 160 or w / h < 1.15:
            return None
        interval = max(SAMPLE_INTERVAL, duration / 360.)
        count = min(360, max(1, math.ceil(duration / interval)))
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if detector.empty():
            return None
        visuals, pairs, singles, motion = [], [], [], []
        mouth_before = [None, None]
        for i in range(count):
            t = start + min(duration - .001, (i + .5) * interval)
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
            ok, frame = capture.read()
            if not ok:
                visuals.append(None)
                pairs.append(None)
                singles.append(None)
                motion.append((0., 0.))
                continue
            height, width = frame.shape[:2]
            scale = min(1., 640. / width)
            small = cv2.resize(frame, (max(2, int(width * scale)), max(2, int(height * scale))))
            grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            thumbnail = cv2.resize(grey, (20, 12)).astype("float32") / 255.
            visuals.append(thumbnail)
            found = detector.detectMultiScale(
                grey, scaleFactor=1.10, minNeighbors=4,
                minSize=(max(20, grey.shape[1] // 27), 20),
            )
            faces = [((x + fw / 2) / grey.shape[1],
                      (y + fh / 2) / grey.shape[0],
                      fw / grey.shape[1], fh / grey.shape[0])
                     for x, y, fw, fh in found]
            pair = _pair(faces)
            pairs.append(pair)
            singles.append(_single_face(faces))
            scores = []
            for j in (0, 1):
                face = pair[j] if pair else None
                if face is None:
                    mouth_before[j] = None
                    scores.append(0.)
                    continue
                cx, cy, fw, fh = face
                x0 = max(0, int((cx - .30 * fw) * grey.shape[1]))
                x1 = min(grey.shape[1], int((cx + .30 * fw) * grey.shape[1]))
                y0 = max(0, int((cy + .08 * fh) * grey.shape[0]))
                y1 = min(grey.shape[0], int((cy + .46 * fh) * grey.shape[0]))
                roi = grey[y0:y1, x0:x1]
                if roi.size < 80:
                    mouth_before[j] = None
                    scores.append(0.)
                    continue
                current = cv2.resize(roi, (48, 24)).astype("float32")
                old = mouth_before[j]
                scores.append(float(np.mean(np.abs(current - old))) if old is not None else 0.)
                mouth_before[j] = current
            motion.append(tuple(scores))

        loudness = _audio_energy(source, start, duration, count, interval, ffmpeg)
        boundaries = scene_boundaries(visuals, pairs, singles)
        boundaries.append(count)
        # In pathological jump-cut videos do not make 100s of filter chains.
        if len(boundaries) - 1 > MAX_SEGMENTS:
            # Group samples evenly; still use independent faces for each group.
            stride = math.ceil(count / MAX_SEGMENTS)
            boundaries = list(range(0, count, stride)) + [count]
        scenes = []
        for i, j in zip(boundaries[:-1], boundaries[1:]):
            a = i * interval
            b = min(duration, j * interval)
            if b - a < .04:
                continue
            scenes.append(_decisions_for_scene(
                i, j, pairs, singles, motion, loudness, mode,
                round(a, 3), round(b, 3), interval,
            ))
        if not scenes:
            return None
        return LayoutPlan(mode, w, h, ((.25, .37), (.75, .37)),
                          segments=tuple(scenes))
    finally:
        capture.release()


def compose_scene_filter(plan, duration: float, width: int, height: int) -> str:
    """Compose timeline-local face crops, then concatenate each shot."""
    from .karo_smart_layouts import LayoutPlan, _crop_geometry, _filter, _focus_expression
    sections = list(plan.segments)
    if not sections:
        return _filter(LayoutPlan(plan.mode, plan.width, plan.height, plan.centers, plan.switches),
                       duration, width, height)
    nodes = []
    outputs = []
    nodes.append("[0:v]fps=30,format=yuv420p,split=%d%s" % (
        len(sections), "".join(f"[src{i}]" for i in range(len(sections)))))
    for i, scene in enumerate(sections):
        length = scene.end - scene.start
        raw = f"shot{i}"
        nodes.append(f"[src{i}]trim=start={scene.start:.3f}:duration={length:.3f},setpts=PTS-STARTPTS[{raw}]")
        if scene.mode == "dual_stack" and len(scene.centers) == 2:
            band = (height * 12 // 100) // 2 * 2
            half = (height - band) // 2
            nodes.append(f"[{raw}]split=2[l{i}][r{i}]")
            # Each panel needs its OWN speaker: a generic fit can reuse most
            # of the landscape frame in both crops, creating duplicate views.
            separation = abs(scene.centers[1][0] - scene.centers[0][0])
            max_panel_w = max(2, int(plan.width * max(.30, min(.55, separation * .98))))
            for side, name, center in (("l", "top", scene.centers[0]), ("r", "bottom", scene.centers[1])):
                cw, ch, x, y = _crop_geometry(plan.width, plan.height, width, half, center, max_panel_w)
                nodes.append(f"[{side}{i}]crop={cw}:{ch}:{x}:{y},scale={width}:{half},setsar=1[{name}{i}]")
            nodes.append(f"color=c=0x111827:s={width}x{band}:r=30:d={length:.3f}[band{i}]")
            nodes.append(f"[top{i}][band{i}][bottom{i}]vstack=inputs=3,format=yuv420p[out{i}]")
        elif scene.mode in {"speaker_focus", "single"} and scene.centers:
            centers = scene.centers if len(scene.centers)==2 else (scene.centers[0], scene.centers[0])
            focus = LayoutPlan("speaker_focus",plan.width,plan.height,centers,scene.switches)
            cw, ch, x = _focus_expression(focus)
            cx, cy = centers[0]
            y = round(max(0, min(plan.height - ch, cy * plan.height - .43 * ch)))
            nodes.append(
                f"[{raw}]crop={cw}:{ch}:x='{x}':y={y},"
                f"scale={width}:{height},setsar=1,format=yuv420p[out{i}]")
        else:
            # Never stack two copies of one subject, or crop a wall when no
            # face is visible. Fit the COMPLETE frame and blur the backdrop.
            nodes.append(f"[{raw}]split=2[bg{i}][fg{i}]")
            nodes.append(f"[bg{i}]scale={width}:{height}:force_original_aspect_ratio=increase,"
                         f"crop={width}:{height},gblur=sigma=14[blur{i}]")
            nodes.append(f"[fg{i}]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                         f"setsar=1[fit{i}]")
            nodes.append(f"[blur{i}][fit{i}]overlay=(W-w)/2:(H-h)/2,"
                         f"setsar=1,format=yuv420p[out{i}]")
        outputs.append(f"[out{i}]")
    nodes.append("".join(outputs) + f"concat=n={len(outputs)}:v=1:a=0,format=yuv420p[vout]")
    return ";".join(nodes)

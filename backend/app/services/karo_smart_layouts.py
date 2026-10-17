"""Clipkaro Smart Layouts: bounded, CPU-based two-person podcast framing.

Inspired by the MIT-licensed OpenShorts split_layout/active_speaker pipeline.
Never invent a second camera: insufficient two-face evidence means classic crop.
The output is a temporary portrait source which the existing, trusted Clipkaro
render/export pipeline then captions, edits and uploads as normal.
"""
from __future__ import annotations

import logging
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("clipkaro.smart_layouts")
VALID_MODES = frozenset({"classic", "auto", "dual_stack", "speaker_focus"})


@dataclass(frozen=True)
class LayoutPlan:
    mode: str
    width: int
    height: int
    centers: tuple[tuple[float, float], tuple[float, float]]
    switches: tuple[tuple[float, int], ...] = ()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _pair(faces: list[tuple[float, float, float, float]]) -> tuple | None:
    """Keep two significant, horizontally separated faces, ordered left/right."""
    valid = sorted((f for f in faces if f[2] >= .045 and f[3] >= .06),
                   key=lambda f: f[2] * f[3], reverse=True)[:3]
    if len(valid) < 2:
        return None
    pair = sorted(valid[:2], key=lambda f: f[0])
    if pair[1][0] - pair[0][0] < .16:
        return None
    return pair[0], pair[1]


def smooth_turns(votes: list[int | None], window: float = .4,
                 min_hold: float = 1.0) -> tuple[tuple[float, int], ...]:
    """Keep speaker changes deliberate: no switches on short interjections."""
    if not votes:
        return ()
    run = max(2, math.ceil(min_hold / window))
    current = next((v for v in votes if v is not None), None)
    if current is None:
        return ()
    changes = [(0., current)]
    pending = None
    streak = 0
    for i, value in enumerate(votes):
        if value is None or value == current:
            pending, streak = None, 0
            continue
        if value != pending:
            pending, streak = value, 1
        else:
            streak += 1
        if streak >= run:
            # Change at the beginning of a confirmed speaking turn.
            change_at = max(0., (i - run + 1) * window)
            if change_at - changes[-1][0] >= min_hold:
                changes.append((round(change_at, 3), value))
                current = value
            pending, streak = None, 0
    return tuple(changes[:42])


def _audio_energy(source: Path, start: float, duration: float, n: int,
                  interval: float, ffmpeg: str):
    import numpy as np
    try:
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-nostdin", "-ss", str(start),
             "-t", str(duration), "-i", str(source), "-vn", "-ac", "1",
             "-ar", "8000", "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=min(180, max(20, int(duration * 2))),
        )
        data = np.frombuffer(result.stdout, dtype=np.int16).astype("float32")
        if not len(data):
            return [0.] * n
        size = max(1, round(8000 * interval))
        values = [float(np.sqrt(np.mean(data[i * size:(i + 1) * size] ** 2)))
                  if len(data[i * size:(i + 1) * size]) else 0. for i in range(n)]
        peak = max(values) or 1.
        return [v / peak for v in values]
    except (OSError, subprocess.TimeoutExpired):
        return [0.] * n


def _normalize_activity(values: list[tuple[float, float]]):
    import numpy as np
    scores = np.asarray(values, dtype=float)
    if scores.size == 0:
        return scores
    lo = np.percentile(scores, 20, axis=0)
    hi = np.percentile(scores, 80, axis=0)
    return np.clip((scores - lo) / np.maximum(hi - lo, 1e-5), 0, 3)


def _detect(source: Path, start: float, duration: float, ffmpeg: str,
            mode: str) -> LayoutPlan | None:
    """Sample bounded frames. Avoid GPU/model downloads on Modal CPU workers."""
    import cv2
    import numpy as np
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return None
    try:
        w, h = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w < 240 or h < 160 or w / h < 1.15:  # Already vertical / unusable.
            return None
        window = .4
        n = min(360, max(1, int(duration / window)))
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if detector.empty():
            return None
        observations = []
        faces_seen = []
        prev_rois = [None, None]
        activity = []
        for i in range(n):
            t = start + (i + .5) * window
            capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = capture.read()
            if not ok:
                observations.append(None)
                activity.append((0., 0.))
                continue
            sh, sw = frame.shape[:2]
            scale = min(1., 640 / sw)
            small = cv2.resize(frame, (int(sw * scale), int(sh * scale)))
            grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            found = detector.detectMultiScale(grey, scaleFactor=1.12, minNeighbors=4,
                                              minSize=(max(22, grey.shape[1] // 24), 22))
            boxes = [(float(x) / grey.shape[1], float(y) / grey.shape[0],
                      float(bw) / grey.shape[1], float(bh) / grey.shape[0])
                     for x, y, bw, bh in found]
            pair = _pair([(x + fw / 2, y + fh / 2, fw, fh) for x, y, fw, fh in boxes])
            observations.append(pair)
            if pair:
                faces_seen.append(pair)
            # Compare aligned, resized mouth regions. Like OpenShorts, normalize
            # each person's movement against their own quiet/loud baseline.
            scores = []
            for j in (0, 1):
                face = pair[j] if pair else None
                if face is None:
                    prev_rois[j] = None
                    scores.append(0.)
                    continue
                cx, cy, fw, fh = face
                x0 = int((cx - fw * .30) * grey.shape[1])
                x1 = int((cx + fw * .30) * grey.shape[1])
                y0 = int((cy + fh * .08) * grey.shape[0])
                y1 = int((cy + fh * .46) * grey.shape[0])
                roi = grey[max(0, y0):min(grey.shape[0], y1),
                           max(0, x0):min(grey.shape[1], x1)]
                if roi.size < 80:
                    scores.append(0.)
                    prev_rois[j] = None
                    continue
                normalized = cv2.resize(roi, (48, 24)).astype("float32")
                old = prev_rois[j]
                scores.append(float(np.mean(np.abs(normalized - old))) if old is not None else 0.)
                prev_rois[j] = normalized
            activity.append(tuple(scores))
        if len(faces_seen) < max(5, int(n * .45)):
            return None
        # Median makes a momentary inaccurate box harmless; no imaginary faces.
        c0 = tuple(float(np.median([row[0][k] for row in faces_seen])) for k in (0, 1))
        c1 = tuple(float(np.median([row[1][k] for row in faces_seen])) for k in (0, 1))
        if c1[0] - c0[0] < .16:
            return None
        centers = (c0, c1)
        energy = _audio_energy(source, start, duration, n, window, ffmpeg)
        normalized = _normalize_activity(activity)
        votes = []
        for i in range(n):
            if observations[i] is None or energy[i] < .18:
                votes.append(None)
                continue
            a, b = float(normalized[i][0]), float(normalized[i][1])
            if a + b < .3 or abs(a - b) / max(a + b, .0001) < .22:
                votes.append(None)
            else:
                votes.append(0 if a > b else 1)
        turns = smooth_turns(votes, window)
        counts = [votes.count(0), votes.count(1)]
        confident = sum(counts)
        conversation = confident >= max(5, n * .12) and min(counts) >= max(2, confident * .18)
        if mode == "auto":
            actual = "dual_stack" if conversation else "speaker_focus" if turns else "dual_stack"
        elif mode == "speaker_focus":
            actual = "speaker_focus" if turns else "dual_stack"
        else:
            actual = "dual_stack"
        return LayoutPlan(actual, w, h, centers, turns)
    finally:
        capture.release()


def _crop_geometry(w: int, h: int, out_w: int, out_h: int,
                   center: tuple[float, float]) -> tuple[int, int, int, int]:
    aspect = out_w / out_h
    crop_w = min(w, int(h * aspect))
    crop_w -= crop_w % 2
    crop_h = min(h, int(crop_w / aspect))
    crop_h -= crop_h % 2
    cx, cy = center
    x = round(_clamp(cx * w - crop_w / 2, 0, w - crop_w))
    y = round(_clamp(cy * h - crop_h * .43, 0, h - crop_h))
    return crop_w, crop_h, x, y


def _focus_expression(plan: LayoutPlan) -> tuple[int, int, str]:
    w, h = plan.width, plan.height
    cw = min(w, int(h * 9 / 16)) // 2 * 2
    ch = min(h, int(cw * 16 / 9)) // 2 * 2
    positions = [int(_clamp(cx * w - cw / 2, 0, w - cw))
                 for cx, _ in plan.centers]
    switches = plan.switches or ((0., 0),)
    expression = str(positions[switches[-1][1]])
    # Ease in/out over 0.4 s to avoid violent crop jumps.
    for j in range(len(switches) - 1, 0, -1):
        t, who = switches[j]
        prior = positions[switches[j - 1][1]]
        following = positions[who]
        begin = max(switches[j - 1][0], t - .20)
        finish = t + .20
        u = f"min(1,max(0,(t-{begin:.3f})/{max(.05,finish-begin):.3f}))"
        ease = f"({u}*{u}*(3-2*{u}))"
        expression = f"if(lt(t,{begin:.3f}),{prior},if(lt(t,{finish:.3f}),({prior}+({following-prior})*{ease}),{expression}))"
    return cw, ch, expression


def _filter(plan: LayoutPlan, duration: float, width: int, height: int) -> str:
    if plan.mode == "speaker_focus":
        cw, ch, x = _focus_expression(plan)
        return (f"[0:v]fps=30,crop={cw}:{ch}:x='{x}':y=0,"
                f"scale={width}:{height},setsar=1,format=yuv420p[vout]")
    band = (height * 12 // 100) // 2 * 2
    half = (height - band) // 2
    left = _crop_geometry(plan.width, plan.height, width, half, plan.centers[0])
    right = _crop_geometry(plan.width, plan.height, width, half, plan.centers[1])
    def panel(name: str, dimensions: tuple, label: str) -> str:
        cw, ch, x, y = dimensions
        return f"[{name}]crop={cw}:{ch}:{x}:{y},scale={width}:{half},setsar=1[{label}]"
    return ("[0:v]fps=30,format=yuv420p,split=2[a][b];"
            + panel("a", left, "top") + ";"
            + panel("b", right, "bottom") + ";"
            + f"color=c=0x111827:s={width}x{band}:r=30:d={duration:.3f}[middle];"
            + "[top][middle][bottom]vstack=inputs=3,format=yuv420p[vout]")


def prepare_smart_layout(source: Path, output: Path, start: float, end: float,
                         mode: str, ffmpeg: str, width: int = 720,
                         height: int = 1280, timeout: int = 600) -> tuple[Path, str] | None:
    """Return (temporary portrait MP4, actual mode); none means safe classic crop."""
    if mode not in VALID_MODES:
        raise ValueError("Unknown Karo Smart Layout mode")
    if mode == "classic" or end <= start:
        return None
    try:
        plan = _detect(source, start, end - start, ffmpeg, mode)
    except Exception as exc:
        logger.warning("Smart Layout detection unavailable; using classic (%s)", type(exc).__name__)
        return None
    if plan is None:
        logger.info("No reliable two-speaker framing found; using classic crop.")
        return None
    if plan.mode == "speaker_focus" and not plan.switches:
        return None
    temp = output.with_name(f".{output.stem}.smart-layout.mp4")
    temp.unlink(missing_ok=True)
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", str(start),
           "-i", str(source), "-t", str(end - start),
           "-filter_complex", _filter(plan, end - start, width, height),
           "-map", "[vout]", "-map", "0:a?", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temp)]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
        if result.returncode or not temp.is_file() or temp.stat().st_size < 1000:
            logger.warning("Smart Layout precompose failed: %s", result.stderr.decode(errors="replace")[-700:])
            temp.unlink(missing_ok=True)
            return None
        logger.info("Karo Smart Layout export mode=%s switches=%d", plan.mode, len(plan.switches))
        return temp, plan.mode
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Smart Layout precompose unavailable (%s)", type(exc).__name__)
        temp.unlink(missing_ok=True)
        return None

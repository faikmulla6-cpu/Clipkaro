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
    segments: tuple[object, ...] = ()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _credible_pair_geometry(left: tuple, right: tuple, min_gap: float) -> bool:
    """Reject an off-row, much smaller background object as a second face.

    The customer's original podcast has a stationary book cover that Haar
    detects as a face at y=.10 while the only human is at y=.33. Both are
    separated horizontally, so horizontal distance alone produces a false
    Dual Stack. This conservative joint test still permits unequal-height
    speakers of similar size; liveness validation remains mandatory.
    """
    if right[0] - left[0] < min_gap:
        return False
    areas = (left[2] * left[3], right[2] * right[3])
    if max(areas) <= 0:
        return False
    if (abs(left[1] - right[1]) > .18
            and min(areas) / max(areas) < .50):
        return False
    return True


def _pair(faces: list[tuple[float, float, float, float]]) -> tuple | None:
    """Keep two significant, horizontally separated faces, ordered left/right."""
    valid = sorted((f for f in faces if f[2] >= .045 and f[3] >= .06),
                   key=lambda f: f[2] * f[3], reverse=True)[:3]
    if len(valid) < 2:
        return None
    pair = sorted(valid[:2], key=lambda f: f[0])
    if not _credible_pair_geometry(pair[0], pair[1], .16):
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
    """Plan each shot independently; two-shot medians must NEVER cross edits."""
    from .karo_smart_scenes import analyze_scenes
    return analyze_scenes(source, start, duration, mode, ffmpeg)


def _crop_geometry(w: int, h: int, out_w: int, out_h: int,
                   center: tuple[float, float],
                   max_crop_w: int | None = None) -> tuple[int, int, int, int]:
    aspect = out_w / out_h
    crop_w = min(w, int(h * aspect), max_crop_w or w)
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
    if plan.segments:
        from .karo_smart_scenes import compose_scene_filter
        return compose_scene_filter(plan, duration, width, height)
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
    if plan.mode == "speaker_focus" and not plan.switches and not plan.segments:
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
            raise RuntimeError("Smart Layout render failed; no incorrect Classic export was substituted.")
        actual_mode = ("dual_stack" if any(s.mode == "dual_stack" for s in plan.segments)
                       else "speaker_focus" if any(s.mode in {"single", "speaker_focus"} for s in plan.segments)
                       else "wide") if plan.segments else plan.mode
        logger.info("Karo Smart Layout export requested=%s actual=%s scenes=%d",
                    mode, actual_mode, len(plan.segments))
        return temp, actual_mode
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Smart Layout precompose unavailable (%s)", type(exc).__name__)
        temp.unlink(missing_ok=True)
        raise RuntimeError("Smart Layout rendering engine is unavailable; try again later.") from exc

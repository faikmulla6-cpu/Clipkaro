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
    # Independent, stable same-frame two-face evidence for the explicitly
    # selected Dual Stack layout. Auto Director's existing decision is intact.
    pair_centers: tuple[tuple[float, float], ...] = ()


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
        # Hard edits often preserve a similar dark podcast backdrop; requiring
        # a 27% whole-frame change leaves two different camera angles grouped
        # together and reuses a crop from the previous speaker. Require
        # supporting face geometry for smaller, genuine visual jumps.
        a_size = a[2] * a[3] if a else 0.
        b_size = b[2] * b[3] if b else 0.
        face_scale_jump = bool(min(a_size, b_size) > 0 and
                               max(a_size, b_size) / min(a_size, b_size) > 2.5)
        is_cut = (jump > .27
                  or (jump > .105 and (pair_flip or location_jump or face_scale_jump))
                  or (jump > .155 and (a is None) != (b is None)))
        # A two-person shot that changes to a close-up may retain a very
        # similar bookshelf backdrop. Require sustained evidence of a
        # genuine camera change instead of trusting one missing Haar frame.
        if not is_cut and jump > .065 and i >= 5 and i + 4 <= n:
            previous = pairs[i-5:i]
            following = pairs[i:i+4]
            before_paired = sum(p is not None for p in previous) >= 4
            after_solo = sum(p is not None for p in following) <= 1
            solo = [s for s in singles[i:i+4] if s is not None]
            paired_sizes = [max(p[0][2]*p[0][3], p[1][2]*p[1][3])
                            for p in previous if p is not None]
            if before_paired and after_solo and len(solo) >= 3 and paired_sizes:
                import statistics
                old_size = statistics.median(paired_sizes)
                new_size = statistics.median(s[2]*s[3] for s in solo)
                is_cut = new_size > max(.006, old_size * 1.6)
        # Some camera cuts retain the same dark studio backdrop. A sustained
        # switch from two small simultaneous faces to one significantly larger
        # close-up is a camera change even when the thumbnail barely moves.
        # Requiring 4/5 observations avoids treating a blink or occlusion
        # as a cut and prevents an old two-face median cropping a bookshelf.
        if not is_cut and i >= 5 and i + 5 <= n:
            before_pairs = [p for p in pairs[i-5:i] if p is not None]
            after_pairs = [p for p in pairs[i:i+5] if p is not None]
            before_solo = [s for s in singles[i-5:i] if s is not None]
            after_solo = [s for s in singles[i:i+5] if s is not None]
            if (pairs[i-1] is not None and pairs[i] is None
                    and len(before_pairs) >= 4 and len(after_pairs) <= 1
                    and len(after_solo) >= 4):
                old_area = max(p[0][2]*p[0][3] for p in before_pairs)
                old_area = max(old_area, max(p[1][2]*p[1][3] for p in before_pairs))
                new_areas = sorted(s[2]*s[3] for s in after_solo)
                # Sustained 4/5 paired -> solo observations establish
                # an actual visibility transition even when both shots have
                # similar-sized faces and a nearly identical backdrop. A
                # single missed Haar detection cannot satisfy this gate.
                is_cut = True
            elif (pairs[i-1] is None and pairs[i] is not None
                  and len(before_pairs) <= 1 and len(after_pairs) >= 4
                  and len(before_solo) >= 4):
                previous_areas = sorted(s[2]*s[3] for s in before_solo)
                new_area = max(p[0][2]*p[0][3] for p in after_pairs)
                new_area = max(new_area, max(p[1][2]*p[1][3] for p in after_pairs))
                # Reverse transition: a solo camera returns to a genuine
                # co-visible two-person shot. Never preserve the old solo
                # crop after this cut or manufacture a second person.
                is_cut = True
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


def _wider_pair(faces: list) -> tuple | None:
    """Small real faces in a wide shot, without guessing any missing person."""
    candidates = sorted(
        (f for f in faces if f[2] >= .030 and f[3] >= .042),
        key=lambda f: f[2] * f[3], reverse=True,
    )[:2]
    if len(candidates) != 2:
        return None
    from .karo_smart_layouts import _credible_pair_geometry
    left, right = sorted(candidates, key=lambda f: f[0])
    return (left, right) if _credible_pair_geometry(left, right, .18) else None


def _appearance_patch(grey, face):
    """Extract stable face-sized pixels; a static poster must NOT be a speaker.

    The detector's bounding box is evidence of facial shape, not of a live
    person. Compare crops only within approximately the same tracked face,
    and do not use optical-flow guesses to invent a second camera.
    """
    import cv2

    cx, cy, fw, fh = face
    width, height = grey.shape[1], grey.shape[0]
    left = max(0, int((cx - fw * .48) * width))
    right = min(width, int((cx + fw * .48) * width))
    top = max(0, int((cy - fh * .48) * height))
    bottom = min(height, int((cy + fh * .48) * height))
    if right-left < 12 or bottom-top < 12:
        return None
    return cv2.resize(grey[top:bottom, left:right], (48, 48)).astype("float32")


def _pair_temporal_activity(grey, pair, previous):
    """Return per-person pixel motion and a tracker for the next sample.

    This is a liveness *quality gate*, never identity or biometric inference.
    It rejects persistent unchanging artwork that Haar can mislabel as a face.
    Brief detector dropouts retain the previous patches so the next matched
    observation can still be compared. A changed position invalidates history.
    """
    import numpy as np

    if pair is None:
        return (0., 0.), previous
    patches = tuple(_appearance_patch(grey, face) for face in pair)
    movement = [0., 0.]
    if previous is not None:
        old_faces, old_patches = previous
        for index, (face, current, old_face, old_patch) in enumerate(
                zip(pair, patches, old_faces, old_patches)):
            if (current is not None and old_patch is not None
                    and abs(face[0]-old_face[0]) <= .09
                    and abs(face[1]-old_face[1]) <= .12):
                movement[index] = float(np.mean(np.abs(current-old_patch)))
    return tuple(movement), (pair, patches)


def _pair_covers_scene(candidates, start_i: int, end_i: int) -> bool:
    """A reliable two-person crop must cover BOTH ends of its shot.

    If both faces are seen for 25 seconds and one disappears for the final
    eight, taking the median of early evidence would leave a fixed empty
    panel over those last seconds. Short detector dropouts remain tolerated.
    """
    count = end_i - start_i
    if count < 10:
        return True
    margin = max(3, math.ceil(count * .2))
    return (
        any(candidates[i] is not None for i in range(start_i, start_i + margin))
        and any(candidates[i] is not None for i in range(end_i - margin, end_i))
    )


def _pair_has_live_motion(candidates, movement, start_i: int, end_i: int) -> bool:
    """Both proposed speakers must change across multiple sampled frames.

    A bookshelf/portrait may produce a stable, confident face rectangle for
    many frames. That is precisely when positional stability alone is unsafe.
    Fail closed to a single face or full-frame shot if either pane is static.
    """
    if movement is None:
        # Older synthetic callers do not provide frame motion; live analysis
        # always supplies it. This preserves pure geometry fixture semantics.
        return True
    observed = [i for i in range(start_i, end_i)
                if candidates[i] is not None]
    if len(observed) < 3:
        return False
    needed = max(2, math.ceil(len(observed) * .18))
    return all(
        sum(bool(movement[i][person] >= 2.2) for i in observed) >= needed
        for person in (0, 1)
    )


def _stable_wide_pair(candidates: list, singles: list,
                      start_i: int, end_i: int,
                      pair_motion: list | None = None) -> tuple[tuple[float, float], ...]:
    """Anchor two *simultaneous* live crops despite intermittent detections.

    A small number of front-facing frames is enough for an unchanged wide
    camera, but a brief cutaway or occasional poster false positive is not.
    Crops continue sampling the same live timestamp; no stills are created.
    """
    import numpy as np
    count = max(1, end_i - start_i)
    found = [(i - start_i, candidates[i]) for i in range(start_i, end_i)
             if candidates[i] is not None]
    minimum = max(3, math.ceil(count * .12))
    if (len(found) < minimum
            or not _pair_covers_scene(candidates, start_i, end_i)
            or not _pair_has_live_motion(candidates, pair_motion, start_i, end_i)):
        return ()
    if count >= 8 and found[-1][0] - found[0][0] < (count - 1) * .55:
        return ()
    # Disallow a solo close-up scene masquerading as a two-person wide shot.
    large = sum(bool(face and face[2] >= .16) for face in singles[start_i:end_i])
    if large > count * .40 and len(found) < count * .55:
        return ()
    coordinates = np.asarray([[[f[0], f[1]] for f in pair]
                              for _, pair in found], dtype=float)
    centers = np.median(coordinates, axis=0)
    stable = np.all(np.abs(coordinates - centers) <= (.10, .14), axis=(1, 2))
    if int(np.count_nonzero(stable)) < minimum or np.mean(stable) < .75:
        return ()
    centers = np.median(coordinates[stable], axis=0)
    if centers[1, 0] - centers[0, 0] < .18:
        return ()
    return tuple((float(p[0]), float(p[1])) for p in centers)


def _decisions_for_scene(
    start_i: int, end_i: int, pairs: list, singles: list,
    scores: list, energy: list, requested: str,
    start_seconds: float, end_seconds: float,
    window: float,
    candidates: list | None = None,
    pair_motion: list | None = None,
) -> Scene:
    import numpy as np
    from .karo_smart_layouts import _normalize_activity, smooth_turns
    count = max(1, end_i - start_i)
    matched = [p for p in pairs[start_i:end_i] if p is not None]
    available = [f for f in singles[start_i:end_i] if f is not None]
    anchor = (_stable_wide_pair(candidates, singles, start_i, end_i, pair_motion)
              if candidates is not None else ())
    paired = candidates if candidates is not None else pairs
    both_live = _pair_has_live_motion(paired, pair_motion, start_i, end_i)
    # Both detected panes must show actual live activity. Never promote a
    # stationary background portrait/poster into a second speaker.
    if (len(matched) >= max(3, math.ceil(count * .55))
            and both_live and (anchor or candidates is None)
            and _pair_covers_scene(pairs, start_i, end_i)):
        # Only crop the verified same-scene pair, not a median of faces from
        # unrelated angles that slipped through a subtle background cut.
        if anchor:
            first, second = anchor
        else:
            # Geometry-only legacy test callers cannot provide live anchors;
            # production always supplies candidate pairs and motion.
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
            return Scene(start_seconds, end_seconds, mode, (first, second), changes,
                         anchor or (first, second))
    if matched and pair_motion is not None and not both_live:
        # In a repeated false two-face detection, prefer the face that MOVES
        # instead of the static poster. This also keeps the original camera
        # timestamp and avoids showing a blank pane.
        votes = [
            sum(1 for i in range(start_i, end_i)
                if paired[i] is not None and pair_motion[i][person] >= 2.2)
            for person in (0, 1)
        ]
        best = 0 if votes[0] > votes[1] else 1
        if votes[best] >= 2:
            live_centers = [
                (float(p[best][0]), float(p[best][1]))
                for p in pairs[start_i:end_i] if p is not None
            ]
            if live_centers:
                face = tuple(float(np.median([point[k] for point in live_centers]))
                             for k in (0, 1))
                return Scene(start_seconds, end_seconds, "single", (face,))
    if len(available) >= max(2, math.ceil(count * .22)):
        # Face position in a close-up is independent of the last wide shot.
        face = tuple(float(np.median([f[k] for f in available])) for k in (0, 1))
        return Scene(start_seconds, end_seconds, "single", (face,), pair_centers=anchor)
    return Scene(start_seconds, end_seconds, "wide", pair_centers=anchor)


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
        visuals, pairs, singles, motion, candidate_pairs = [], [], [], [], []
        candidate_motion = []
        previous_pair_appearance = None
        mouth_before = [None, None]
        for i in range(count):
            t = start + min(duration - .001, (i + .5) * interval)
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
            ok, frame = capture.read()
            if not ok:
                visuals.append(None)
                pairs.append(None)
                singles.append(None)
                candidate_pairs.append(None)
                candidate_motion.append((0., 0.))
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
            wider = pair or _wider_pair(faces)
            if wider is None:
                # Wide cameras often show smaller/dimmer faces. This second
                # pass is evidence ONLY for explicit Dual Stack, and cannot
                # affect Auto Director's already-tuned shot decisions.
                enhanced = cv2.equalizeHist(grey)
                extra = detector.detectMultiScale(
                    enhanced, scaleFactor=1.08, minNeighbors=3,
                    minSize=(max(18, grey.shape[1] // 34), 18),
                )
                more_faces = [((x + fw / 2) / grey.shape[1],
                               (y + fh / 2) / grey.shape[0],
                               fw / grey.shape[1], fh / grey.shape[0])
                              for x, y, fw, fh in extra]
                wider = _wider_pair(more_faces)
            candidate_pairs.append(wider)
            live_delta, previous_pair_appearance = _pair_temporal_activity(
                grey, wider, previous_pair_appearance)
            candidate_motion.append(live_delta)
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
            # Merging unrelated shots to meet a limit reintroduces stale
            # cross-cut speaker crops. Prefer safe Classic to false Dual Stack.
            logger.warning("Smart Layout has more than %d camera shots; decline unsafe plan", MAX_SEGMENTS)
            return None
        scenes = []
        for i, j in zip(boundaries[:-1], boundaries[1:]):
            a = i * interval
            b = min(duration, j * interval)
            if b - a < .04:
                continue
            scenes.append(_decisions_for_scene(
                i, j, pairs, singles, motion, loudness, mode,
                round(a, 3), round(b, 3), interval, candidate_pairs,
                candidate_motion,
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

"""Render the authenticated v2 Smart Layout timeline, never a second detection.

FFmpeg consumes exactly the source-pixel crops that the editor paints.
The caller supplies a private, validated server-generated plan, not user
provided raw coordinates or a remote path.
"""
from __future__ import annotations

import math
from typing import Any

from app.services.smart_layout_contract import UnsafeLayoutPlan, validate_serialized_plan


def _even(value: float) -> int:
    n = int(round(value))
    return n if n % 2 == 0 else n - 1


def _filter_focus(scene: dict[str, Any], crop: list[int]) -> str:
    transitions = scene["switches"]
    positions = [int(point[0]) for point in scene["crops"]]
    if not transitions:
        return str(positions[0])
    start = float(scene["start"])
    expr = str(positions[int(transitions[-1][1])])
    # Easing must use scene-local timestamps (trim resets PTS).
    for j in range(len(transitions)-1, 0, -1):
        time, who = transitions[j]
        previous = int(transitions[j-1][1])
        initial = positions[previous]
        following = positions[int(who)]
        begin = max(float(transitions[j-1][0]), float(time) - .2)
        end = float(time) + .2
        u = f"min(1,max(0,(t-{begin:.3f})/{max(.05,end-begin):.3f}))"
        easing = f"({u}*{u}*(3-2*{u}))"
        expr = (f"if(lt(t,{begin:.3f}),{initial},"
                f"if(lt(t,{end:.3f}),({initial}+({following-initial})*{easing}),{expr}))")
    return expr


def _verify_export_plan(plan: dict[str, Any], source_start: float, duration: float) -> None:
    validate_serialized_plan(plan)
    if not isinstance(plan, dict) or plan.get("version") != 2:
        raise UnsafeLayoutPlan("Unsupported Smart Layout export plan")
    if plan.get("requested_mode") not in {"auto", "dual_stack", "speaker_focus"}:
        raise UnsafeLayoutPlan("Unknown Smart Layout mode")
    if abs(float(plan.get("source_start", -1)) - source_start) > .01:
        raise UnsafeLayoutPlan("Smart Layout source timestamp differs from export")
    if abs(float(plan.get("duration", -1)) - duration) > .01:
        raise UnsafeLayoutPlan("Smart Layout duration differs from export")
    w = plan.get("source_width")
    h = plan.get("source_height")
    if (not isinstance(w, int) or not isinstance(h, int) or
            w < 240 or h < 160 or w > 16384 or h > 16384):
        raise UnsafeLayoutPlan("Smart Layout source dimensions invalid")
    sections = plan.get("scenes")
    if not isinstance(sections, list) or not (1 <= len(sections) <= 24):
        raise UnsafeLayoutPlan("Invalid Smart Layout scene count")
    cursor = 0.
    for scene in sections:
        if not isinstance(scene, dict):
            raise UnsafeLayoutPlan("Invalid scene entry")
        a = float(scene["start"])
        b = float(scene["end"])
        if not math.isfinite(a+b) or abs(a - cursor) > .065 or b-a < .03:
            raise UnsafeLayoutPlan("Smart Layout scene timeline discontinuity")
        crops = scene.get("crops")
        kind = scene.get("layout")
        if kind not in {"dual_stack", "single", "speaker_focus", "wide"}:
            raise UnsafeLayoutPlan("Invalid scene mode")
        required = 2 if kind in {"dual_stack", "speaker_focus"} else 1
        if not isinstance(crops, list) or len(crops) != required:
            raise UnsafeLayoutPlan("Inconsistent scene face count")
        for crop in crops:
            if not isinstance(crop, list) or len(crop) != 4:
                raise UnsafeLayoutPlan("Invalid crop")
            x,y,cw,ch = crop
            if not all(isinstance(val, int) and not isinstance(val, bool) for val in crop):
                raise UnsafeLayoutPlan("Noninteger crop")
            if min(x,y) < 0 or cw < 2 or ch < 2 or x+cw > w or y+ch > h:
                raise UnsafeLayoutPlan("Crop exceeded original source")
        if kind == "dual_stack" and crops[0] == crops[1]:
            raise UnsafeLayoutPlan("Dual Stack cannot duplicate one crop")
        cursor = b
    if abs(cursor-duration) > .065:
        raise UnsafeLayoutPlan("Smart Layout scene timeline does not cover export")


def compose_v2_filter(plan: dict[str, Any], duration: float,
                      output_width: int, output_height: int) -> str:
    """Generate a filtergraph using only the canonical cached source-pixel crop.

    Source frame coordinates remain unchanged even if paid plans deliver a
    bigger final resolution. The output scaling never invents face detection.
    """
    _verify_export_plan(plan, float(plan["source_start"]), duration)
    if output_width % 2 or output_height % 2 or output_width < 240 or output_height < 400:
        raise UnsafeLayoutPlan("Unsupported output dimensions")
    sections = plan["scenes"]
    fragments = [
        f"[0:v]fps=30,format=yuv420p,split={len(sections)}"
        + "".join(f"[src{i}]" for i in range(len(sections)))
    ]
    results = []
    for i, scene in enumerate(sections):
        t = float(scene["start"])
        length = float(scene["end"])-t
        fragments.append(f"[src{i}]trim=start={t:.3f}:duration={length:.3f},setpts=PTS-STARTPTS[shot{i}]")
        mode = scene["layout"]
        if mode == "dual_stack":
            band = (output_height * 12 // 100) // 2 * 2
            half = (output_height-band)//2
            fragments.append(f"[shot{i}]split=2[a{i}][b{i}]")
            for name,src,crop in (("top",f"a{i}",scene["crops"][0]),("bottom",f"b{i}",scene["crops"][1])):
                x,y,w,h = crop
                fragments.append(f"[{src}]crop={w}:{h}:{x}:{y},scale={output_width}:{half},setsar=1[{name}{i}]")
            fragments.append(f"color=c=0x111827:s={output_width}x{band}:r=30:d={length:.3f}[band{i}]")
            fragments.append(f"[top{i}][band{i}][bottom{i}]vstack=inputs=3,setsar=1,format=yuv420p[out{i}]")
        elif mode in {"single","speaker_focus"}:
            x,y,w,h = scene["crops"][0]
            focus = _filter_focus(scene,scene["crops"][0]) if mode=="speaker_focus" else str(x)
            fragments.append(f"[shot{i}]crop={w}:{h}:x='{focus}':y={y},"
                             f"scale={output_width}:{output_height},setsar=1,format=yuv420p[out{i}]")
        else:
            fragments.append(f"[shot{i}]split=2[bg{i}][fg{i}]")
            fragments.append(f"[bg{i}]scale={output_width}:{output_height}:force_original_aspect_ratio=increase,"
                             f"crop={output_width}:{output_height},gblur=sigma=14[blur{i}]")
            fragments.append(f"[fg{i}]scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,"
                             f"setsar=1[fit{i}]")
            fragments.append(f"[blur{i}][fit{i}]overlay=(W-w)/2:(H-h)/2,"
                             f"setsar=1,format=yuv420p[out{i}]")
        results.append(f"[out{i}]")
    fragments.append("".join(results)+f"concat=n={len(sections)}:v=1:a=0,format=yuv420p[vout]")
    return ";".join(fragments)


def precompose_v2(source, output, plan: dict[str, Any], ffmpeg: str,
                  width: int, height: int, timeout: int) -> tuple[Any, str]:
    """Encode one private intermediate with real source and unchanged audio.

    No fallback to Classic when user explicitly asked for Smart Layout.
    """
    import subprocess
    source_start = float(plan["source_start"])
    duration = float(plan["duration"])
    graph = compose_v2_filter(plan, duration, width, height)
    temp = output.with_name(f".{output.stem}.smart-v2.mp4")
    temp.unlink(missing_ok=True)
    try:
        command = [
            ffmpeg, "-nostdin","-v","error","-y","-ss",str(source_start),
            "-i",str(source),"-t",str(duration),"-filter_complex",graph,
            "-map","[vout]","-map","0:a?","-c:v","libx264",
            "-preset","veryfast","-crf","22","-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","128k","-movflags","+faststart",str(temp),
        ]
        output_result = subprocess.run(command,stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,check=False,timeout=timeout)
        if output_result.returncode or not temp.is_file() or temp.stat().st_size < 1000:
            raise RuntimeError("Smart Layout v2 could not render this video.")
        actual = ("dual_stack" if any(scene["layout"]=="dual_stack" for scene in plan["scenes"])
                  else "speaker_focus" if any(scene["layout"] in {"single","speaker_focus"} for scene in plan["scenes"])
                  else "wide")
        return temp,actual
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError("Smart Layout v2 preview/export composition failed.") from exc

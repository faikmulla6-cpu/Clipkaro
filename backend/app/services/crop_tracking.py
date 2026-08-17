from typing import Any


def smooth_crop_keyframes(keyframes: list[dict[str, Any]], duration: float,
                          fallback: float = 50) -> list[dict[str, float]]:
    """Normalize crop observations and cap abrupt horizontal motion."""
    rows = sorted(({"time": max(0.0, min(float(k["time"]), duration)),
                    "focus_x": max(0.0, min(float(k["focus_x"]), 100.0))} for k in keyframes),
                  key=lambda item: item["time"])
    if not rows: return [{"time": 0.0, "focus_x": fallback}, {"time": duration, "focus_x": fallback}]
    if rows[0]["time"] > 0: rows.insert(0, {"time": 0.0, "focus_x": rows[0]["focus_x"]})
    if rows[-1]["time"] < duration: rows.append({"time": duration, "focus_x": rows[-1]["focus_x"]})
    output = [rows[0]]
    for row in rows[1:]:
        previous = output[-1]
        elapsed = max(row["time"] - previous["time"], .01)
        max_move = 18.0 * elapsed  # dead-smooth crop; avoids visual snapping.
        delta = max(-max_move, min(row["focus_x"] - previous["focus_x"], max_move))
        output.append({"time": row["time"], "focus_x": previous["focus_x"] + delta})
    return output


def ffmpeg_focus_expression(keyframes: list[dict[str, float]], duration: float) -> str:
    """Create a piecewise-linear FFmpeg expression in the 0..1 focus domain."""
    rows = smooth_crop_keyframes(keyframes, duration)
    expression = f"{rows[-1]['focus_x']/100:.5f}"
    for left, right in reversed(list(zip(rows, rows[1:]))):
        span = max(right["time"] - left["time"], .001)
        start, delta = left["focus_x"] / 100, (right["focus_x"] - left["focus_x"]) / 100
        value = f"({start:.5f}+{delta:.5f}*(t-{left['time']:.3f})/{span:.3f})"
        expression = f"if(lt(t\\,{right['time']:.3f})\\,{value}\\,{expression})"
    return expression

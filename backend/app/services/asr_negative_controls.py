from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.video import find_media_tool


NEGATIVE_CONTROLS = ("silence", "noise_only", "tone_only")


def create_negative_control(output: Path, kind: str, *, seconds: float = 30.0) -> Path:
    """Create audio that contains no speech and therefore must not yield a transcript."""
    if kind not in NEGATIVE_CONTROLS:
        raise ValueError(f"Unknown ASR negative control: {kind}")
    if seconds < 5:
        raise ValueError("Negative controls must be at least 5 seconds long.")
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for ASR negative controls.")

    if kind == "silence":
        source = "anullsrc=r=16000:cl=mono"
    elif kind == "noise_only":
        source = "anoisesrc=color=pink:amplitude=0.22:r=16000"
    else:
        source = "sine=frequency=330:sample_rate=16000"

    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            ffmpeg, "-nostdin", "-y", "-f", "lavfi", "-i", source,
            "-t", f"{seconds:.3f}", "-c:a", "aac", "-b:a", "64k", str(output),
        ],
        capture_output=True,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        raise RuntimeError(
            f"FFmpeg could not create ASR {kind} control: "
            + proc.stderr.decode(errors="ignore")[-700:]
        )
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"ASR {kind} negative control is invalid.")
    return output

import asyncio
import csv
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from .video import find_media_tool
from app.core.config import get_settings

TESSDATA = Path(__file__).resolve().parents[2] / "assets" / "tessdata"


async def detect_burned_captions(video: Path, duration: float, samples: int = 8) -> dict:
    """Detect persistent text in the lower picture area using sampled OCR, not filename heuristics."""
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg or not shutil.which("tesseract") or duration <= 0:
        return {"detected": False, "confidence": 0.0, "reason": "ocr_unavailable"}

    def run() -> dict:
        with tempfile.TemporaryDirectory(prefix="clipkaro-caption-scan-") as folder:
            root = Path(folder)
            interval = max(duration / samples, .5)
            try:
                decode = subprocess.run([
                    ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(video),
                    "-vf", f"fps=1/{interval:.3f},crop=iw:ih*0.50:0:ih*0.48,scale=1440:-1,unsharp=5:5:1.2",
                    "-frames:v", str(samples), str(root / "frame-%02d.png")
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
                   timeout=max(30, min(300, int(get_settings().media_process_timeout_seconds))))
            except subprocess.TimeoutExpired:
                return {"detected": False, "confidence": 0.0, "reason": "frame_scan_timeout"}
            if decode.returncode != 0:
                return {"detected": False, "confidence": 0.0, "reason": "frame_scan_failed"}
            hits, checked, caption_y = 0, 0, []
            for frame in sorted(root.glob("frame-*.png")):
                checked += 1
                try:
                    proc = subprocess.run([
                        "tesseract", str(frame), "stdout", "--tessdata-dir", str(TESSDATA),
                        "-l", "hin+eng", "--psm", "11", "tsv"
                    ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=20)
                except subprocess.TimeoutExpired:
                    continue
                if proc.returncode: continue
                rows = csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", "ignore")), delimiter="\t")
                parsed = list(rows)
                page = next((row for row in parsed if row.get("level") == "1"), {})
                page_height = max(float(page.get("height") or 0), 1)
                accepted = [row for row in parsed if row.get("text", "").strip()
                            and float(row.get("conf", -1) or -1) >= 15]
                tokens = [row.get("text", "").strip() for row in accepted]
                # OCR is run over y=.48..98 of the source. Preserve the detected band so
                # the renderer can cover burned captions instead of stacking another layer.
                caption_y.extend(.48 + .50 * (float(row.get("top") or 0) / page_height)
                                 for row in accepted)
                if sum(len(token) for token in tokens) >= 4: hits += 1
            confidence = hits / max(checked, 1)
            # Restrict masking to the platform-unsafe lower quarter. Text detected
            # higher in the picture can be signage, a face-adjacent label, or a prior
            # ClipKaro preview and must never cause a giant black panel.
            band_start = max(.76, min(.92, min(caption_y, default=.80) - .025))
            return {"detected": checked >= 3 and confidence >= .35,
                    "confidence": round(confidence, 3), "sampled_frames": checked,
                    "band_start": round(band_start, 3),
                    "reason": "persistent_lower_third_text" if confidence >= .35 else "no_persistent_text"}
    return await asyncio.to_thread(run)

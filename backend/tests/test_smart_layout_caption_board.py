"""Regression: real Dual Stack captions belong on the center board.

No production data, storage, B2 keys, export jobs or billing required.
Tests real India Pop word positions and matching vector-pill backgrounds.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.services.smart_layout_captions import position_ass_by_scene


_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: IndiaPop,Lato,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,5,20,20,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
_WORD_STATE = [
    r"Dialogue: 0,0:00:00.00,0:00:03.00,IndiaPop,,0,0,0,,{\an7\pos(300,1532)\p1\1c&H0057FFDF\bord0\shad0}m 0 0 l 160 0 l 160 80 l 0 80",
    r"Dialogue: 1,0:00:00.00,0:00:03.00,IndiaPop,,0,0,0,,{\an5\pos(380,1572)\1c&H00FFFFFF}YOU",
    r"Dialogue: 1,0:00:00.00,0:00:03.00,IndiaPop,,0,0,0,,{\an5\pos(650,1572)\1c&H00FFFFFF}KNOW",
    r"Dialogue: 1,0:00:00.00,0:00:03.00,IndiaPop,,0,0,0,,{\an5\pos(540,1642)\1c&H00FFFFFF}EVERYTHING",
]
_SCENES = [
    {"start": 0., "end": 1., "caption_zone": "bottom"},
    {"start": 1., "end": 4., "caption_zone": "middle"},
    {"start": 4., "end": 6., "caption_zone": "bottom"},
]


class DualStackCaptionBoardTests(unittest.TestCase):
    def _file(self, folder: str, events: list[str]) -> Path:
        file = Path(folder) / "captions.ass"
        file.write_text(_HEADER + "\n".join(events) + "\n", encoding="utf-8")
        return file

    def test_india_pop_pill_and_all_words_translate_together(self):
        with tempfile.TemporaryDirectory() as folder:
            file = self._file(folder, _WORD_STATE)
            position_ass_by_scene(file, _SCENES, 1080, 1920, None)
            lines = file.read_text(encoding="utf-8-sig").splitlines()
            middle = [line for line in lines
                      if line.startswith("Dialogue:") and ",0:00:01.00,0:00:03.00," in line]
            original = [line for line in lines
                        if line.startswith("Dialogue:") and ",0:00:00.00,0:00:01.00," in line]
            self.assertEqual(len(middle), 4)
            self.assertEqual(len(original), 4)
            self.assertTrue(any(r"\an7\pos(300,885)\p1" in line for line in middle))
            self.assertTrue(any(r"\an5\pos(380,925)" in line for line in middle))
            self.assertTrue(any(r"\an5\pos(650,925)" in line for line in middle))
            self.assertTrue(any(r"\an5\pos(540,995)" in line for line in middle))
            self.assertTrue(any(r"\an7\pos(300,1532)\p1" in line for line in original))
            self.assertTrue(all(line.count(r"\pos(") == 1 for line in middle))
            self.assertEqual(sum("Dialogue:" in line for line in lines), 8)

    def test_plain_caption_without_position_gets_centered_once(self):
        with tempfile.TemporaryDirectory() as folder:
            file = self._file(folder, [
                r"Dialogue: 0,0:00:00.20,0:00:04.50,Caption,,0,0,0,,{\c&H00FF0000}HELLO"
            ])
            position_ass_by_scene(file, _SCENES, 1080, 1920, None)
            rows = [line for line in file.read_text(encoding="utf-8-sig").splitlines()
                    if line.startswith("Dialogue:")]
            self.assertEqual(len(rows), 3)
            self.assertIn(r"{\an5\pos(540,960)}", rows[1])
            self.assertNotIn(r"\pos(", rows[0])
            self.assertNotIn(r"\pos(", rows[2])

    def test_retained_smart_edit_ranges_shift_caption_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            file = self._file(folder, [
                r"Dialogue: 1,0:00:01.90,0:00:02.40,IndiaPop,,0,0,0,,{\an5\pos(540,1580)\1c&H00FFFFFF}KEEP"
            ])
            position_ass_by_scene(file, _SCENES, 1080, 1920,
                                  [{"start": 0., "end": 2.}, {"start": 3., "end": 5.}])
            text = file.read_text(encoding="utf-8-sig")
            self.assertIn("0:00:02.00,0:00:02.40", text)
            self.assertIn(r"\pos(540,960)", text)

    def test_actual_ffmpeg_text_and_pill_draw_inside_strip(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("FFmpeg is not installed")
        with tempfile.TemporaryDirectory() as folder:
            file = self._file(folder, _WORD_STATE)
            position_ass_by_scene(
                file, [{"start": 0., "end": 3., "caption_zone": "middle"}],
                1080, 1920, None,
            )
            output = Path(folder) / "frame.png"
            video_filter = (
                "drawbox=x=0:y=844:w=1080:h=232:color=0x111827:t=fill,"
                "ass=filename=captions.ass"
            )
            result = subprocess.run([
                ffmpeg, "-nostdin", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=0x545454:s=1080x1920:r=1:d=1",
                "-vf", video_filter, "-frames:v", "1", str(output),
            ], capture_output=True, timeout=45, cwd=folder)
            self.assertEqual(result.returncode, 0,
                             result.stderr.decode("utf-8", "replace")[-600:])
            # Decode a small crop of the render using FFmpeg itself. We do
            # not need Pillow, cloud secrets or a customer's private video.
            crop = subprocess.run([
                ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(output),
                "-vf", "crop=540:200:270:860",
                "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
            ], capture_output=True, timeout=30, check=True)
            pixels = crop.stdout
            self.assertEqual(len(pixels), 540 * 200 * 3)
            # The center contains actual visible caption pixels, not only
            # the empty 0x111827 band. A former duplicate-\pos regression
            # leaves the center dark and text over the lower speaker.
            changed = 0
            for i in range(0, len(pixels), 24):
                rgb = pixels[i:i+3]
                if len(rgb) == 3 and (max(rgb) > 125):
                    changed += 1
            self.assertGreater(changed, 100)


if __name__ == "__main__":
    unittest.main()

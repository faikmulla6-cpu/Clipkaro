"""CPU-only Karo Smart Layout verification, including actual FFmpeg output."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.karo_smart_layouts import (
    LayoutPlan, _crop_geometry, _filter, _focus_expression, _pair,
    prepare_smart_layout, smooth_turns,
)


class LayoutTests(unittest.TestCase):
    def test_two_faces_have_to_be_separate(self):
        self.assertIsNone(_pair([(0.25, .3, .1, .2)]))
        self.assertIsNone(_pair([(0.25, .3, .1, .2), (0.31, .3, .1, .2)]))
        self.assertIsNotNone(_pair([(0.25, .3, .1, .2), (0.74, .3, .1, .2)]))

    def test_rapid_interjection_cannot_steal_frame(self):
        turns = smooth_turns([0] * 7 + [1] + [0] * 7)
        self.assertEqual(turns, ((0., 0),))

    def test_confirmed_turn_changes(self):
        turns = smooth_turns([0] * 7 + [1] * 8 + [0] * 8)
        self.assertEqual([speaker for _, speaker in turns], [0, 1, 0])

    def test_crops_are_bounded(self):
        cw, ch, x, y = _crop_geometry(1920, 1080, 720, 560, (.9, .3))
        self.assertGreater(cw, 0)
        self.assertGreater(ch, 0)
        self.assertLessEqual(x + cw, 1920)
        self.assertLessEqual(y + ch, 1080)

    def test_split_reserves_separate_caption_band(self):
        plan = LayoutPlan("dual_stack", 1280, 720, ((.25, .3), (.75, .3)))
        graph = _filter(plan, 3., 720, 1280)
        self.assertIn("vstack=inputs=3", graph)
        self.assertIn("color=c=0x111827", graph)

    def test_focus_uses_eased_switch_not_hard_jump(self):
        plan = LayoutPlan("speaker_focus", 1280, 720, ((.25,.3),(.75,.3)),
                          ((0.,0),(2.,1)))
        _, _, expr = _focus_expression(plan)
        self.assertIn("lt(t,1.800)", expr)
        self.assertIn("3-2*", expr)

    def test_bad_mode_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                prepare_smart_layout(Path("nothing.mp4"), Path(tmp)/"x.mp4",
                                     0, 3, "unsafe", "ffmpeg")

    def test_no_faces_falls_back_without_creating_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "export.mp4"
            with patch("app.services.karo_smart_layouts._detect", return_value=None):
                self.assertIsNone(prepare_smart_layout(Path("unknown.mp4"), output,
                                                        0, 30, "auto", "ffmpeg"))
            self.assertFalse(output.exists())

    def test_real_ffmpeg_stacked_and_focus(self):
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("FFmpeg/FFprobe not available")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "podcast.mp4"
            # Artificial split-color video verifies both output framing branches.
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", "color=c=red:s=640x720:r=15:d=3",
                   "-f", "lavfi", "-i", "color=c=blue:s=640x720:r=15:d=3",
                   "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                   "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]",
                   "-map", "[v]", "-map", "2:a", "-c:v", "libx264",
                   "-preset", "ultrafast", "-c:a", "aac", str(src)]
            subprocess.run(cmd, check=True, timeout=90)
            for mode in ("dual_stack", "speaker_focus"):
                plan = LayoutPlan(mode, 1280, 720, ((.25, .32), (.75, .32)),
                                  ((0., 0), (1.6, 1)) if mode == "speaker_focus" else ())
                with patch("app.services.karo_smart_layouts._detect", return_value=plan):
                    output = Path(tmp) / (mode + ".mp4")
                    result = prepare_smart_layout(src, output, 0, 3, mode, ffmpeg,
                                                  width=360, height=640, timeout=90)
                    self.assertIsNotNone(result, mode)
                    temp, resolved = result
                    self.assertEqual(resolved, mode)
                    probe = subprocess.run(
                        [ffprobe, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height",
                         "-of", "json", str(temp)],
                        capture_output=True, text=True, check=True, timeout=15,
                    )
                    self.assertEqual(json.loads(probe.stdout)["streams"][0],
                                     {"width": 360, "height": 640})
                    temp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

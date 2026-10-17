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


class SceneAwareTests(unittest.TestCase):
    def test_each_camera_shot_has_independent_layout(self):
        from app.services.karo_smart_scenes import _decisions_for_scene
        both = ((.24,.37,.10,.14),(.77,.36,.10,.14))
        # Wide two-person angle, then cut to a solo speaker close-up.
        pairs = [both]*8 + [None]*8
        single = [both[0]]*8 + [(.72,.34,.16,.28)]*8
        scores = [(9.,1.)]*5+[(1.,9.)]*3+[(0.,0.)]*8
        energy = [1.]*16
        stacked = _decisions_for_scene(0,8,pairs,single,scores,energy,
                                      "dual_stack",0.,3.2,.4)
        closeup = _decisions_for_scene(8,16,pairs,single,scores,energy,
                                      "dual_stack",3.2,6.4,.4)
        self.assertEqual(stacked.mode, "dual_stack")
        self.assertEqual(closeup.mode, "single")
        self.assertGreater(closeup.centers[0][0],.65)

    def test_no_detected_face_uses_safe_full_frame_instead_of_wall_crop(self):
        from app.services.karo_smart_scenes import _decisions_for_scene
        scene = _decisions_for_scene(0,6,[None]*6,[None]*6,
                                     [(0.,0.)]*6,[0.]*6,"dual_stack",0.,2.4,.4)
        self.assertEqual(scene.mode,"wide")

    def test_camera_cut_is_detected_even_when_faces_change(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries
        a=np.full((12,20),.15,dtype="float32")
        b=np.full((12,20),.57,dtype="float32")
        both=((.2,.3,.10,.2),(.8,.3,.10,.2))
        edges=scene_boundaries([a]*8+[b]*8,[both]*8+[None]*8,
                               [both[0]]*8+[(.8,.35,.15,.3)]*8)
        self.assertEqual(edges,[0,8])

    def test_real_ffmpeg_per_scene_split_and_solo_no_seam(self):
        import shutil
        from app.services.karo_smart_scenes import Scene
        ffmpeg=shutil.which("ffmpeg")
        ffprobe=shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("FFmpeg not available")
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"scene-source.mp4"
            # Deliberately changing camera scene: first split source, then
            # identical all-blue source. The second scene MUST NOT duplicate
            # two static original speaker crops as Dual Stack.
            command=[ffmpeg,"-hide_banner","-loglevel","error","-y",
               "-f","lavfi","-i","color=c=red:s=320x720:r=30:d=2",
               "-f","lavfi","-i","color=c=blue:s=320x720:r=30:d=2",
               "-f","lavfi","-i","color=c=blue:s=640x720:r=30:d=2",
               "-f","lavfi","-i","sine=frequency=440:duration=4",
               "-filter_complex","[0:v][1:v]hstack=inputs=2[wide];[wide][2:v]concat=n=2:v=1:a=0,setsar=5120/5121[src]",
               "-map","[src]","-map","3:a","-c:v","libx264","-preset","ultrafast",
               "-c:a","aac",str(src)]
            subprocess.run(command,check=True,timeout=70)
            plan=LayoutPlan("dual_stack",640,720,((.24,.32),(.76,.32)),
                segments=(
                    Scene(0.,2.,"dual_stack",((.25,.33),(.75,.33))),
                    Scene(2.,4.,"single",((.75,.33),)),
                ))
            with patch("app.services.karo_smart_layouts._detect",return_value=plan):
                outcome=prepare_smart_layout(src,Path(tmp)/"target.mp4",0.,4.,
                                              "dual_stack",ffmpeg,width=360,
                                              height=640,timeout=90)
            self.assertIsNotNone(outcome)
            resulting,_=outcome
            import cv2
            cap=cv2.VideoCapture(str(resulting))
            try:
                cap.set(cv2.CAP_PROP_POS_MSEC,700)
                ok,first=cap.read()
                self.assertTrue(ok)
                cap.set(cv2.CAP_PROP_POS_MSEC,2700)
                ok,second=cap.read()
                self.assertTrue(ok)
            finally:
                cap.release()
            # BGR: red top, blue bottom in first scene. Solo second shot
            # is uniformly blue, not a red/blue two-panel composite.
            self.assertGreater(int(first[100,180,2]),170)
            self.assertGreater(int(first[550,180,0]),170)
            self.assertLess(int(second[100,180,2]),70)
            self.assertLess(int(second[550,180,2]),70)
            resulting.unlink(missing_ok=True)


    def test_explicit_smart_layout_failure_does_not_silently_export_classic(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=LayoutPlan("dual_stack",1280,720,((.24,.31),(.77,.31)))
            with patch("app.services.karo_smart_layouts._detect",return_value=plan):
                with patch("app.services.karo_smart_layouts.subprocess.run") as run:
                    run.return_value.returncode=1
                    run.return_value.stderr=b"synthetic FFmpeg failure"
                    with self.assertRaisesRegex(RuntimeError,"Smart Layout render failed"):
                        prepare_smart_layout(Path(tmp)/"in.mp4",Path(tmp)/"out.mp4",
                            0.,3.,"dual_stack","ffmpeg")
            self.assertFalse((Path(tmp)/"out.mp4").exists())

    def test_scene_filter_contains_all_timeline_shots(self):
        from app.services.karo_smart_scenes import Scene,compose_scene_filter
        plan=LayoutPlan("dual_stack",1280,720,((.24,.37),(.76,.37)),
            segments=(Scene(0.,3.,"wide"),Scene(3.,6.,"single",((.75,.33),)),
                     Scene(6.,8.,"dual_stack",((.25,.32),(.76,.31)))))
        graph=compose_scene_filter(plan,8.,360,640)
        self.assertIn("concat=n=3",graph)
        self.assertIn("trim=start=6.000:duration=2.000",graph)
        self.assertIn("setsar=1,format=yuv420p[out0]",graph)
        self.assertEqual(graph.count("vstack=inputs=3"),1)

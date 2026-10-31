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

    def test_studio_book_is_not_a_second_live_person(self):
        from app.services.karo_smart_scenes import _wider_pair
        # Normalized detections reproduced from the source file.
        book = (.287, .104, .102, .181)
        presenter = (.512, .324, .189, .336)
        self.assertIsNone(_pair([book, presenter]))
        self.assertIsNone(_wider_pair([book, presenter]))
        # Real simultaneous speakers remain eligible for split layout.
        left = (.264, .372, .200, .356)
        right = (.688, .383, .203, .361)
        self.assertIsNotNone(_pair([left, right]))
        self.assertIsNotNone(_wider_pair([left, right]))
        # A legitimate change in elevation alone must not be rejected.
        self.assertIsNotNone(_pair([
            (.22, .12, .17, .24), (.73, .40, .17, .24)]))

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
    def test_short_pair_to_solo_cut_does_not_stack_a_bookshelf(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries, _decisions_for_scene
        from app.services.smart_layout_variants import all_layout_variants

        left = (.25, .34, .09, .13)
        right = (.75, .34, .09, .13)
        solo = (.75, .34, .21, .29)
        # Seven 400-ms samples: a real pair for 1.6s, followed by a close-up
        # for 1.2s with the SAME bookshelf/background. The old short-scene
        # exemption allowed an obsolete left crop to stay on screen.
        pairs = [(left, right)] * 4 + [None] * 3
        singles = [left] * 4 + [solo] * 3
        visuals = [np.full((12, 20), .28, dtype="float32")] * 7
        self.assertEqual(scene_boundaries(visuals, pairs, singles), [0, 4])
        movement = [(0., 0.)] + [(7., 8.)] * 3 + [(0., 0.)] * 3
        mixed = _decisions_for_scene(
            0, 7, pairs, singles, [(7., 8.)] * 7, [1.] * 7,
            "auto", 0., 2.8, .4, pairs, movement,
        )
        self.assertEqual(mixed.pair_centers, (),
                         "weak cross-cut evidence must never seed a split")
        variants = all_layout_variants(
            LayoutPlan("auto", 1280, 720, ((.25, .34), (.75, .34)),
                       segments=(mixed,)),
            source_start=0., duration=2.8,
        )
        self.assertNotEqual(variants["dual_stack"]["scenes"][0]["layout"], "dual_stack")
        # The actual shot-aware plan can still show both real speakers BEFORE
        # the cut, while reverting to a full-height solo crop immediately after.
        cuts = [0, 4, 7]
        shots = tuple(_decisions_for_scene(
            i, j, pairs, singles, [(7., 8.)] * 7, [1.] * 7,
            "auto", i * .4, j * .4, .4, pairs, movement,
        ) for i, j in zip(cuts[:-1], cuts[1:]))
        result = all_layout_variants(
            LayoutPlan("auto", 1280, 720, ((.25, .34), (.75, .34)),
                       segments=shots),
            source_start=0., duration=2.8,
        )
        self.assertEqual(
            [s["layout"] for s in result["dual_stack"]["scenes"]],
            ["dual_stack", "single"],
        )
        self.assertEqual(result["dual_stack"]["scenes"][1]["caption_zone"], "bottom")

    def test_short_solo_to_pair_cut_is_detected_with_unchanged_backdrop(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries
        left, right = (.25, .34, .09, .13), (.75, .34, .09, .13)
        solo = (.75, .34, .21, .29)
        frames = [np.full((12, 20), .28, dtype="float32")] * 7
        pairs = [None] * 4 + [(left, right)] * 3
        singles = [solo] * 4 + [left] * 3
        self.assertEqual(scene_boundaries(frames, pairs, singles), [0, 4])

    def test_long_detection_gap_cannot_keep_two_stale_panels(self):
        from app.services.karo_smart_scenes import _stable_wide_pair
        left = (.25, .34, .09, .13)
        right = (.75, .34, .09, .13)
        pair = (left, right)
        candidates = [pair] * 8 + [None] * 11 + [pair] * 9
        motion = [(7., 8.) if p is not None else (0., 0.)
                  for p in candidates]
        self.assertEqual(
            _stable_wide_pair(candidates, [left] * len(candidates),
                              0, len(candidates), motion),
            (), "two distant appearances cannot bridge a solo camera cut",
        )

    def test_good_initial_pair_cannot_leave_empty_panel_at_end(self):
        from app.services.karo_smart_scenes import _decisions_for_scene
        from app.services.smart_layout_variants import all_layout_variants
        first = (.25,.35,.085,.13)
        second = (.77,.35,.085,.13)
        solo = (.77,.35,.20,.26)
        # This is the regression observed in the 67-second customer export:
        # a long valid two-person shot, then several seconds with only one
        # speaker. The existing majority rule would incorrectly keep split.
        n = 35
        paired = [(first, second)] * 27 + [None] * 8
        singles = [first] * 27 + [solo] * 8
        movement = [(6., 7.)] * 27 + [(0., 0.)] * 8
        scene = _decisions_for_scene(
            0,n,paired,singles,[(6.,7.)]*n,[1.]*n,
            "auto",0.,14.,.4,paired,movement,
        )
        self.assertNotEqual(scene.mode, "dual_stack")
        self.assertEqual(scene.pair_centers, ())
        variants = all_layout_variants(
            LayoutPlan("auto",1280,720,((.25,.35),(.75,.35)),
                       segments=(scene,)),
            source_start=0,duration=14,
        )
        self.assertNotEqual(variants["dual_stack"]["scenes"][0]["layout"],"dual_stack")

    def test_sustained_closeup_after_two_person_shot_creates_boundary(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries
        first = np.full((12,20),.25,dtype="float32")
        second = np.full((12,20),.34,dtype="float32")
        a,b = (.25,.32,.08,.12),(.75,.32,.08,.12)
        bigger = (.76,.35,.20,.28)
        n = 20
        visuals = [first]*n + [second]*8
        pairs = [(a,b)]*n + [None]*8
        singles = [a]*n + [bigger]*8
        self.assertEqual(scene_boundaries(visuals,pairs,singles),[0,20])

    def test_two_people_to_one_to_two_without_visual_background_change(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries, _decisions_for_scene
        from app.services.smart_layout_variants import all_layout_variants
        a, b = (.23,.34,.12,.20), (.77,.35,.12,.20)
        both = (a, b)
        # Both heads can occupy essentially the same position and have the
        # same size across adjacent camera shots. Scene decisions must follow
        # sustained co-visibility, NOT depend on an arbitrary scale jump.
        pairs = [both]*15 + [None]*12 + [both]*15
        singles = [a]*15 + [b]*12 + [a]*15
        visuals = [np.full((12,20), .24, dtype="float32")]*42
        cuts = scene_boundaries(visuals, pairs, singles)
        self.assertEqual(cuts, [0,15,27],
                         "A+B -> B only -> A+B must become three independent shots")
        scores = ([(9.,1.)]*7 + [(1.,9.)]*8 + [(0.,0.)]*12
                  + [(9.,1.)]*7 + [(1.,9.)]*8)
        movements = [(6.,7.)]*15 + [(0.,0.)]*12 + [(6.,7.)]*15
        segments = []
        for i, j in zip(cuts, cuts[1:]+[42]):
            segments.append(_decisions_for_scene(
                i,j,pairs,singles,scores,[1.]*42,"auto",
                i*.4,j*.4,.4,pairs,movements))
        self.assertEqual([s.mode for s in segments],
                         ["dual_stack","single","dual_stack"])
        result = all_layout_variants(
            LayoutPlan("auto",1280,720,((.23,.34),(.77,.35)),
                       segments=tuple(segments)),
            source_start=120.,duration=16.8)
        self.assertEqual(
            [s["layout"] for s in result["auto"]["scenes"]],
            ["dual_stack","single","dual_stack"])
        self.assertEqual(
            [s["layout"] for s in result["dual_stack"]["scenes"]],
            ["dual_stack","single","dual_stack"])
        self.assertEqual(
            [s["layout"] for s in result["speaker_focus"]["scenes"]],
            ["speaker_focus","single","speaker_focus"])
        for mode, payload in result.items():
            self.assertEqual(payload["scenes"][1]["caption_zone"],"bottom",mode)
            self.assertEqual(len(payload["scenes"][1]["crops"]),1,mode)
            self.assertEqual(payload["source_start"],120.,mode)
            self.assertEqual(payload["duration"],16.8,mode)

    def test_closeup_cut_with_unchanged_backdrop_does_not_keep_old_pair(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries
        same = [np.full((12, 20), .25, dtype="float32")] * 30
        pair = ((.25, .33, .08, .12), (.75, .33, .08, .12))
        solo = (.76, .33, .22, .27)
        # Background nearly identical before/after edit. Sustained geometry
        # is sufficient evidence that old two-person crops are now unsafe.
        cuts = scene_boundaries(same, [pair]*16+[None]*14,
                                [pair[0]]*16+[solo]*14)
        self.assertEqual(cuts, [0, 16])

    def test_single_missed_face_does_not_fragment_dual_stack(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries
        a,b=(.25,.32,.08,.12),(.75,.32,.08,.12)
        one=(.75,.32,.20,.25)
        pair=[(a,b)]*24
        pair[12]=None
        singles=[a]*24
        singles[12]=one
        same=[np.full((12,20),.26,dtype="float32")]*24
        self.assertEqual(scene_boundaries(same,pair,singles),[0])

    def test_static_poster_does_not_qualify_as_second_speaker(self):
        from app.services.karo_smart_scenes import _decisions_for_scene
        from app.services.smart_layout_variants import all_layout_variants
        fake = (.24, .33, .085, .12)
        moving = (.77, .37, .17, .25)
        frames = 20
        pair = (fake, moving)
        # Haar sees two face-like rectangles every frame, but the poster is
        # perfectly stationary while the real guest speaks.
        evidence = [pair] * frames
        movement = [(0., 8.)] * frames
        scene = _decisions_for_scene(
            0, frames, evidence, [moving]*frames,
            [(0., 8.)]*frames, [1.]*frames, "auto",
            0., 8., .4, evidence, movement,
        )
        self.assertEqual(scene.mode, "single")
        self.assertAlmostEqual(scene.centers[0][0], moving[0])
        self.assertEqual(scene.pair_centers, ())
        plan = LayoutPlan("auto", 1280, 720, ((.25,.35),(.75,.35)),
                          segments=(scene,))
        plans = all_layout_variants(plan, source_start=0, duration=8)
        for mode in plans:
            self.assertEqual(plans[mode]["scenes"][0]["layout"], "single",
                             "Explicit Dual Stack must fail safe too")

    def test_live_pair_keeps_genuine_split(self):
        from app.services.karo_smart_scenes import _decisions_for_scene
        one = (.25, .3, .09, .12)
        two = (.76, .32, .09, .12)
        pair = (one, two)
        samples = 15
        scene = _decisions_for_scene(
            0, samples, [pair]*samples, [one]*samples,
            [(4.,7.)]*samples, [1.]*samples, "dual_stack",
            0., 6., .4, [pair]*samples, [(4.,7.)]*samples,
        )
        self.assertEqual(scene.mode, "dual_stack")
        self.assertEqual(len(scene.centers), 2)

    def test_temporal_motion_detects_static_artwork(self):
        import numpy as np
        import cv2
        from app.services.karo_smart_scenes import _pair_temporal_activity
        face_a = (.25, .4, .16, .25)
        face_b = (.75, .4, .16, .25)
        pair = (face_a, face_b)
        base = np.full((240,480), 90, dtype="uint8")
        rng = np.random.default_rng(7)
        a, prev = _pair_temporal_activity(base, pair, None)
        self.assertEqual(a, (0.,0.))
        other = base.copy()
        other[64:128, 320:400] = rng.integers(0,255,size=(64,80),dtype="uint8")
        result, _ = _pair_temporal_activity(other, pair, prev)
        self.assertLess(result[0], 0.01)
        self.assertGreater(result[1], 2.2)

    def test_medium_visual_cut_with_face_change_creates_independent_shot(self):
        import numpy as np
        from app.services.karo_smart_scenes import scene_boundaries
        first = np.full((12,20),.23,dtype="float32")
        second = np.full((12,20),.36,dtype="float32")
        pair = ((.25,.34,.09,.12),(.74,.34,.09,.12))
        boundaries = scene_boundaries(
            [first]*9+[second]*9,
            [pair]*9+[None]*9,
            [pair[0]]*9+[(.75,.34,.19,.25)]*9,
        )
        self.assertEqual(boundaries, [0,9])

    def test_intermittent_two_face_evidence_enables_only_explicit_live_dual(self):
        from app.services.karo_smart_scenes import _decisions_for_scene
        from app.services.smart_layout_variants import all_layout_variants
        samples = 25
        small_a, small_b = (.23, .35, .052, .075), (.77, .36, .053, .072)
        # Both people are in the continuous wide camera shot. Haar only
        # recognizes the faces in seven of the 25 sampled frames.
        intermittent = [None] * samples
        for index in (0, 4, 8, 12, 16, 20, 24):
            intermittent[index] = (small_a, small_b)
        strict = [None] * samples
        singles = [small_a] * samples
        scene = _decisions_for_scene(
            0, samples, strict, singles, [(0., 0.)] * samples,
            [0.] * samples, "auto", 0., 10., .4, intermittent,
        )
        self.assertEqual(scene.mode, "single", "keep Auto Director unchanged")
        self.assertEqual(len(scene.pair_centers), 2)
        plan = LayoutPlan("auto", 1280, 720, ((.25, .36), (.75, .36)),
                          segments=(scene,))
        layouts = all_layout_variants(plan, source_start=0, duration=10)
        self.assertEqual(layouts["auto"]["scenes"][0]["layout"], "single")
        self.assertEqual(layouts["speaker_focus"]["scenes"][0]["layout"], "single")
        self.assertEqual(layouts["dual_stack"]["scenes"][0]["layout"], "dual_stack")
        self.assertEqual(layouts["dual_stack"]["scenes"][0]["caption_zone"], "middle")
        self.assertNotEqual(*layouts["dual_stack"]["scenes"][0]["crops"])

    def test_brief_or_unstable_two_face_evidence_never_creates_live_dual(self):
        from app.services.karo_smart_scenes import _stable_wide_pair, _wider_pair
        a, b = (.25, .35, .04, .065), (.75, .37, .04, .065)
        self.assertIsNotNone(_wider_pair([a, b]))
        self.assertIsNone(_wider_pair([a]))
        self.assertIsNone(_wider_pair([a, (.31, .37, .04, .065)]))
        frames = [None] * 25
        for index in (0, 1, 2, 3, 4, 5, 6):
            frames[index] = (a, b)
        self.assertEqual(_stable_wide_pair(frames, [a]*25, 0, 25), (),
                         "brief opening wide shot is not an all-scene anchor")
        for index in (0, 4, 8, 12, 16, 20, 24):
            frames[index] = (a, b)
        self.assertEqual(_stable_wide_pair(frames, [(.4,.3,.23,.28)]*25, 0, 25), (),
                         "single close-ups must not be split using weak pair evidence")

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


class FrameExactCutTests(unittest.TestCase):
    """A five-frame camera shot must not inherit the preceding camera crop."""

    def test_exact_scene_ranges_preserve_five_frame_intermediate_shot(self):
        from app.services.karo_smart_scenes import _scene_time_ranges, _decisions_for_scene
        ranges = _scene_time_ranges(
            count=9, interval=.4, duration=3.6,
            coarse_boundaries=[0, 4], hard_cuts=(1.2, 1.366667),
        )
        self.assertEqual(len(ranges), 3)
        self.assertAlmostEqual(ranges[1][0], 1.2)
        self.assertAlmostEqual(ranges[1][1], 1.366667)
        self.assertEqual(ranges[1][2:], (3, 3))
        # With no sample inside this 167-ms camera shot, display the entire
        # source frame instead of guessing a stale speaker or pair location.
        cutaway = _decisions_for_scene(
            3, 3, [None] * 9, [None] * 9, [(0., 0.)] * 9,
            [0.] * 9, "auto", 1.2, 1.366667, .4,
        )
        self.assertEqual(cutaway.mode, "wide")

    def test_ffmpeg_finds_both_edges_of_a_five_frame_camera_shot(self):
        import shutil
        from app.services.karo_smart_scenes import _frame_scene_cuts
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "five-frame-camera.mp4"
            cmd = [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=1.2",
                "-f", "lavfi", "-i", "color=c=green:s=640x360:r=30:d=0.166667",
                "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30:d=1.2",
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[out]",
                "-map", "[out]", "-c:v", "libx264", "-preset", "ultrafast",
                str(src),
            ]
            subprocess.run(cmd, check=True, timeout=90)
            cuts = _frame_scene_cuts(src, 0., 2.566667, ffmpeg)
            self.assertIsNotNone(cuts)
            self.assertEqual(len(cuts), 2, cuts)
            self.assertAlmostEqual(cuts[0], 1.2, delta=.035)
            self.assertAlmostEqual(cuts[1], 1.366667, delta=.035)
            # Source seek times must stay clip-relative, not global PTS.
            offset = _frame_scene_cuts(src, .5, 1.8, ffmpeg)
            self.assertEqual(len(offset), 2, offset)
            self.assertAlmostEqual(offset[0], .7, delta=.035)
            self.assertAlmostEqual(offset[1], .866667, delta=.035)
            self.assertIsNone(_frame_scene_cuts(src, 0., 2.5, "missing-ffmpeg-binary"))

    def test_five_frame_camera_shot_survives_actual_scene_render(self):
        """Do not lose or borrow even one frame at exact scene boundaries."""
        import shutil
        from app.services.karo_smart_scenes import (
            Scene, compose_scene_filter, _frame_scene_cuts,
        )
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "three-shots.mp4"
            make = [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=1.2",
                "-f", "lavfi", "-i", "color=c=green:s=640x360:r=30:d=0.166667",
                "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30:d=1.2",
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[out]",
                "-map", "[out]", "-c:v", "libx264", "-preset", "ultrafast", str(src),
            ]
            subprocess.run(make, check=True, timeout=90)
            cuts = _frame_scene_cuts(src, 0., 77/30, ffmpeg)
            self.assertEqual(len(cuts), 2, cuts)
            plan = LayoutPlan("dual_stack", 640, 360, ((.25, .3), (.75, .3)),
                segments=(Scene(0., cuts[0], "wide"),
                          Scene(cuts[0], cuts[1], "wide"),
                          Scene(cuts[1], 77/30, "wide")))
            graph = compose_scene_filter(plan, 77/30, 90, 160)
            cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-i", str(src), "-filter_complex", graph, "-map", "[vout]",
                   "-an", "-fps_mode", "passthrough",
                   "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
            out = subprocess.run(cmd, capture_output=True, timeout=90)
            self.assertEqual(out.returncode, 0, out.stderr[-700:])
            frame_size = 90 * 160 * 3
            self.assertEqual(len(out.stdout) % frame_size, 0)
            colors = []
            for pos in range(0, len(out.stdout), frame_size):
                p = pos + (80 * 90 + 45) * 3
                rgb = out.stdout[p:p+3]
                colors.append("RGB"[max(range(3), key=lambda i: rgb[i])])
            self.assertEqual(colors, ["R"] * 36 + ["G"] * 5 + ["B"] * 36)

"""Security and geometry regression tests for the Smart Layout v2 contract.

No network, payment account, database, object storage or media API is required.
"""
from __future__ import annotations

from types import SimpleNamespace as S
import math
import unittest

from app.services.smart_layout_contract import (
    UnsafeLayoutPlan, from_media_plan, scene_at,
)


def shot(start, end, mode, centers=(), switches=()):
    return S(start=start, end=end, mode=mode,
             centers=centers, switches=switches)


def plan(*scenes, mode="auto", width=1280, height=720):
    return S(mode=mode, width=width, height=height, segments=scenes)


class SafeTimelineContractTests(unittest.TestCase):
    def test_real_camera_cut_stays_single_without_duplicating_face(self):
        raw = plan(
            shot(0, 3, "dual_stack", ((.24, .34), (.75, .34))),
            shot(3, 5, "single", ((.73, .30),)),
            shot(5, 8, "wide"),
        )
        data = from_media_plan(raw, source_start=523.46, duration=8)
        self.assertEqual(data["version"], 2)
        self.assertEqual([s["layout"] for s in data["scenes"]],
                         ["dual_stack", "single", "wide"])
        self.assertEqual([len(s["crops"]) for s in data["scenes"]], [2, 1, 1])
        self.assertNotEqual(data["scenes"][0]["crops"][0],
                            data["scenes"][0]["crops"][1])
        self.assertEqual(data["scenes"][1]["caption_zone"], "bottom")
        self.assertEqual(data["scenes"][0]["caption_zone"], "middle")
        self.assertEqual(scene_at(data, 4.0)["layout"], "single")
        self.assertEqual(scene_at(data, 1.3)["layout"], "dual_stack")
        self.assertIsNone(scene_at(data, 8.01))

    def test_focus_speaker_switches_are_scene_relative(self):
        raw = plan(shot(0, 4, "speaker_focus",
                        ((.19, .3), (.83, .4)),
                        ((0., 0), (2.0, 1))), mode="speaker_focus")
        data = from_media_plan(raw, source_start=12.0, duration=4)
        self.assertEqual(data["scenes"][0]["switches"], [[0., 0], [2., 1]])
        self.assertNotEqual(data["scenes"][0]["crops"][0],
                            data["scenes"][0]["crops"][1])

    def test_source_boundaries_hold_for_all_panels(self):
        raw = plan(shot(0, 3, "dual_stack", ((.02, .06), (.98, .94))))
        data = from_media_plan(raw, source_start=0, duration=3)
        for crop in data["scenes"][0]["crops"]:
            x, y, w, h = crop
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x+w, 1280)
            self.assertLessEqual(y+h, 720)

    def test_unverified_face_pair_is_rejected(self):
        with self.assertRaisesRegex(UnsafeLayoutPlan, "two separate"):
            from_media_plan(plan(shot(0, 2, "dual_stack", ((.3,.4),(.35,.5)))),
                            source_start=0, duration=2)
        with self.assertRaisesRegex(UnsafeLayoutPlan, "two separate"):
            from_media_plan(plan(shot(0, 2, "dual_stack", ((.4,.3),))),
                            source_start=0, duration=2)

    def test_scene_time_must_have_no_gap_or_overlap(self):
        for second_start in (1.8, 2.2):
            with self.assertRaises(UnsafeLayoutPlan):
                from_media_plan(plan(shot(0,2,"wide"), shot(second_start,4,"wide")),
                                source_start=0, duration=4)

    def test_no_non_finite_positions_or_times(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.assertRaises(UnsafeLayoutPlan):
                from_media_plan(plan(shot(0, 2,"single",((bad,.4),))),
                                source_start=0,duration=2)
            with self.assertRaises(UnsafeLayoutPlan):
                from_media_plan(plan(shot(0, 2,"wide")),
                                source_start=bad,duration=2)

    def test_no_oversized_clip_or_unbounded_scene_count(self):
        with self.assertRaises(UnsafeLayoutPlan):
            from_media_plan(plan(shot(0, 200, "wide")),
                            source_start=0, duration=200)
        too_many = [shot(i*.1,(i+1)*.1,"wide") for i in range(25)]
        with self.assertRaises(UnsafeLayoutPlan):
            from_media_plan(plan(*too_many), source_start=0,duration=2.5)

    def test_switches_cannot_reference_third_person_or_reverse_time(self):
        invalid = ((0,0), (1,2))
        with self.assertRaises(UnsafeLayoutPlan):
            from_media_plan(plan(shot(0,3,"speaker_focus",
                        ((.2,.3),(.8,.3)),invalid)),
                        source_start=0,duration=3)
        invalid = ((2,1), (1,0))
        with self.assertRaises(UnsafeLayoutPlan):
            from_media_plan(plan(shot(0,3,"speaker_focus",
                        ((.2,.3),(.8,.3)),invalid)),
                        source_start=0,duration=3)

    def test_malformed_and_hostile_mode_fails_closed(self):
        for mode in (None, "classic", "file:///secrets", "<script>", ""):
            with self.assertRaises(UnsafeLayoutPlan):
                from_media_plan(plan(shot(0,1,"wide"),mode=mode),
                                source_start=0,duration=1)

    def test_response_has_no_private_user_storage_information(self):
        result = from_media_plan(plan(shot(0,2,"single",((.5,.3),))),
                                 source_start=0,duration=2)
        self.assertEqual(set(result), {
            "version", "requested_mode", "source_width", "source_height",
            "source_start", "duration", "preview_width", "preview_height", "scenes",
        })
        self.assertNotIn("user_id", repr(result))
        self.assertNotIn("file_path", repr(result))



class PrivateAnalysisCacheTests(unittest.TestCase):
    def test_customer_source_and_trim_are_part_of_cache_identity(self):
        import uuid
        from app.services.smart_layout_cache import AnalysisIdentity, private_plan_key, safe_owner_key
        uid, project, clip, video = [str(uuid.uuid4()) for _ in range(4)]
        item = AnalysisIdentity(uid, project, clip, video, "etag:v1", 523.46, 583.02)
        path = private_plan_key(item)
        self.assertTrue(safe_owner_key(path, uid, project))
        self.assertFalse(safe_owner_key(path, str(uuid.uuid4()), project))
        self.assertFalse(safe_owner_key(path, uid, str(uuid.uuid4())))
        self.assertNotIn("etag:v1", path)
        self.assertTrue(path.startswith(f"users/{uid}/projects/{project}/smart-layout/v2/"))
        other_generation = AnalysisIdentity(uid, project, clip, video, "etag:v2", 523.46, 583.02)
        other_trim = AnalysisIdentity(uid, project, clip, video, "etag:v1", 523.46, 580.02)
        other_video = AnalysisIdentity(uid, project, clip, str(uuid.uuid4()), "etag:v1", 523.46, 583.02)
        for changed in (other_generation, other_trim, other_video):
            self.assertNotEqual(private_plan_key(changed), path)

    def test_path_and_duration_injection_fails_closed(self):
        import uuid
        from app.services.smart_layout_cache import AnalysisIdentity, private_plan_key
        uid, project, clip, video = [str(uuid.uuid4()) for _ in range(4)]
        for generation in ("", "bad\\nfilename", "x"*161):
            with self.assertRaises(ValueError):
                private_plan_key(AnalysisIdentity(uid, project, clip, video, generation, 0, 10))
        for start, end in ((10, 9), (0, 181), (0, float("nan")), (-1, 10)):
            with self.assertRaises(ValueError):
                private_plan_key(AnalysisIdentity(uid, project, clip, video, "v1", start, end))
        with self.assertRaises(ValueError):
            private_plan_key(AnalysisIdentity("../../secrets", project, clip, video, "v1", 0, 10))


if __name__ == "__main__":
    unittest.main()

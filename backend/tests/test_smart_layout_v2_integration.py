"""V2 renderer and caption contract tests: no customer or external services."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from app.services.smart_layout_contract import UnsafeLayoutPlan, validate_serialized_plan
from app.services.smart_layout_render_v2 import compose_v2_filter, precompose_v2
from app.services.smart_layout_captions import position_ass_by_scene
from app.services.smart_layout_variants import all_layout_variants
from app.services.karo_smart_scenes import Scene
from app.services.karo_smart_layouts import LayoutPlan


def timeline():
    plan=LayoutPlan("auto",640,360,((.26,.3),(.76,.3)),segments=(
      Scene(0.,2.,"dual_stack",((.26,.33),(.76,.33)), ((0.,0),(1.,1))),
      Scene(2.,4.,"single",((.78,.33),)),
    ))
    return all_layout_variants(plan, source_start=0, duration=4)


class SmartV2UnitTests(unittest.TestCase):
    def test_split_preserves_speaker_turns_for_active_top_panel(self):
        bundle=timeline()
        self.assertEqual(bundle["auto"]["scenes"][0]["switches"],[[0.,0],[1.,1]])
        self.assertEqual(bundle["dual_stack"]["scenes"][0]["switches"],[[0.,0],[1.,1]])
        self.assertEqual(bundle["speaker_focus"]["scenes"][0]["switches"],[[0.,0],[1.,1]])
        for mode in bundle:
            validate_serialized_plan(bundle[mode])

    def test_geometry_ffmpeg_uses_exact_preview_source_pixels(self):
        plan=timeline()["dual_stack"]
        graph=compose_v2_filter(plan, 4, 360, 640)
        for coord in plan["scenes"][0]["crops"]:
            x,y,w,h=coord
            self.assertIn(f"crop={w}:{h}:{x}:{y}",graph)
        self.assertIn("concat=n=3",graph)
        self.assertIn("setsar=1",graph)
        self.assertIn("[band0]",graph)

    def test_corrupt_cache_rejected_before_ffmpeg(self):
        normal=timeline()["auto"]
        mutations=[
          ("source_width",0),("requested_mode","nonsense"),
          ("source_start",float("nan")),
        ]
        for field,value in mutations:
            copy=json.loads(json.dumps(normal))
            copy[field]=value
            with self.assertRaises(UnsafeLayoutPlan):
                validate_serialized_plan(copy)
        bad=json.loads(json.dumps(normal))
        bad["scenes"][0]["crops"][1]=bad["scenes"][0]["crops"][0]
        with self.assertRaises(UnsafeLayoutPlan):
            validate_serialized_plan(bad)

    def test_scene_local_ass_caption_repositioning_with_removed_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"captions.ass"
            p.write_text("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                         "Dialogue: 0,0:00:00.50,0:00:02.50,Caption,,0,0,0,,hello world\n",
                         encoding="utf-8")
            position_ass_by_scene(p,timeline()["auto"]["scenes"],360,640,None)
            value=p.read_text(encoding="utf-8-sig")
            self.assertEqual(value.count("Dialogue:"),2)
            self.assertIn(r"{\an5\pos(180,320)}hello world",value)
            self.assertIn("Dialogue: 0,0:00:02.00,0:00:02.50",value)
            self.assertEqual(value.count(r"\pos(180,320)"),1)

            p.write_text("[Events]\nDialogue: 0,0:00:00.50,0:00:01.50,Caption,,0,0,0,,hello\n",
                         encoding="utf-8")
            position_ass_by_scene(p,timeline()["auto"]["scenes"],360,640,
                                  [{"start":0.,"end":1.},{"start":3.,"end":4.}])
            txt=p.read_text(encoding="utf-8-sig")
            self.assertEqual(txt.count("Dialogue:"),2)
            self.assertIn(r"\pos(180,320)",txt)
            self.assertIn("0:00:01.00,0:00:01.50",txt)

    def test_real_ffmpeg_wide_then_speaker(self):
        ffmpeg=shutil.which("ffmpeg")
        ffprobe=shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"src.mp4"
            output=Path(tmp)/"final.mp4"
            # Source is red left + blue right. One shot uses 2 separate
            # subjects; the next keeps only the blue right speaker.
            input_args=[ffmpeg,"-hide_banner","-loglevel","error","-y",
              "-f","lavfi","-i","color=c=red:s=320x360:r=30:d=4",
              "-f","lavfi","-i","color=c=blue:s=320x360:r=30:d=4",
              "-filter_complex","[0:v][1:v]hstack=inputs=2[v]",
              "-map","[v]","-c:v","libx264","-preset","ultrafast",str(a)]
            subprocess.run(input_args,check=True,capture_output=True,timeout=50)
            out,actual=precompose_v2(a,output,timeline()["dual_stack"],ffmpeg,360,640,90)
            self.assertEqual(actual,"dual_stack")
            self.assertTrue(out.is_file())
            probe=subprocess.run([ffprobe,"-v","error","-select_streams","v:0",
               "-show_entries","stream=width,height","-of","json",str(out)],
               check=True,capture_output=True,timeout=20)
            info=json.loads(probe.stdout)
            self.assertEqual((info["streams"][0]["width"],info["streams"][0]["height"]),(360,640))
            out.unlink(missing_ok=True)


    def test_both_live_panels_advance_through_same_original_timeline(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "two-live-speakers.mp4"
            output = Path(tmp) / "output.mp4"
            # Two different moving test patterns share one 2-second video
            # timeline, just like the user's continuous wide podcast source.
            subprocess.run([
                ffmpeg, "-nostdin", "-v", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x360:rate=15:duration=2",
                "-f", "lavfi", "-i", "testsrc=size=320x360:rate=15:duration=2",
                "-filter_complex", "[0:v][1:v]hstack=inputs=2,format=yuv420p[v]",
                "-map", "[v]", "-c:v", "libx264", "-threads", "2",
                "-preset", "ultrafast", str(source),
            ], check=True, capture_output=True, timeout=30)
            evidence = LayoutPlan("auto", 640, 360, ((.25,.34),(.75,.34)),
                                  segments=(Scene(0.,2.,"dual_stack",
                                                  ((.25,.34),(.75,.34))),))
            plan = all_layout_variants(evidence, source_start=0, duration=2)["dual_stack"]
            result, actual = precompose_v2(source, output, plan, ffmpeg, 360, 640, 70)
            self.assertEqual(actual, "dual_stack")
            for label, crop in (("top", "crop=360:260:0:0"),
                                ("bottom", "crop=360:260:0:380")):
                output_hashes = subprocess.run([
                    ffmpeg, "-v", "error", "-i", str(result),
                    "-vf", crop, "-an", "-f", "framemd5", "-",
                ], check=True, capture_output=True, text=True, timeout=30).stdout
                frames = [row.split(",")[-1].strip() for row in output_hashes.splitlines()
                          if row and not row.startswith("#")]
                self.assertGreater(len(set(frames)), 3,
                                   f"{label} panel must show moving video, never a frozen face")
            result.unlink(missing_ok=True)


if __name__=="__main__":
    unittest.main()


class LayoutPreferencePersistenceTests(unittest.TestCase):
    def test_layout_mode_survives_smart_edit_normalization(self):
        from app.services.smart_edit import normalize_edit_plan
        selection=normalize_edit_plan({
            "version":2,"removed_ranges":[{"start":.4,"end":.7,"reason":"pause"}],
            "split_points":[2.0],"segment_order":[1,0],
            "layout_mode":"speaker_focus",
        }, 4.)
        self.assertEqual(selection["layout_mode"],"speaker_focus")
        self.assertEqual(selection["segment_order"],[1,0])
        self.assertEqual(selection["removed_ranges"][0]["reason"],"pause")
        invalid=normalize_edit_plan({"layout_mode":"file:///private/key"},4.)
        self.assertNotIn("layout_mode",invalid)


class HighResolutionSplitSafetyTests(unittest.TestCase):
    def test_even_chroma_boundaries_at_customer_export_resolutions(self):
        plan = timeline()["dual_stack"]
        for width,height,band,half in ((360,640,76,282),(720,1280,152,564),(1080,1920,232,844)):
            graph = compose_v2_filter(plan,4.,width,height)
            self.assertIn(f"scale={width}:{half}",graph)
            self.assertIn(f"s={width}x{band}",graph)
            self.assertEqual((height-band)//2,half)
            self.assertEqual(half % 2,0)

    def test_1080p_real_ffmpeg_split_and_audio_survive_scene_boundaries(self):
        ffmpeg=shutil.which("ffmpeg")
        ffprobe=shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"input.mp4"
            result_output=Path(tmp)/"result.mp4"
            cmd=[ffmpeg,"-nostdin","-v","error","-y",
                 "-f","lavfi","-i","color=c=red:s=320x360:r=30:d=4",
                 "-f","lavfi","-i","color=c=blue:s=320x360:r=30:d=4",
                 "-f","lavfi","-i","sine=frequency=440:sample_rate=44100:duration=4",
                 "-filter_complex","[0:v][1:v]hstack=inputs=2[v]",
                 "-map","[v]","-map","2:a","-c:v","libx264","-threads","2",
                 "-preset","ultrafast","-c:a","aac",str(source)]
            subprocess.run(cmd,check=True,capture_output=True,timeout=40)
            output,layout=precompose_v2(
                source,result_output,timeline()["dual_stack"],
                ffmpeg,1080,1920,timeout=140,
            )
            self.assertEqual(layout,"dual_stack")
            probe=subprocess.run([ffprobe,"-v","error","-show_entries",
                        "format=duration:stream=codec_type,width,height",
                        "-of","json",str(output)],
                        check=True,capture_output=True,text=True,timeout=25)
            info=json.loads(probe.stdout)
            video=next(x for x in info["streams"] if x["codec_type"]=="video")
            self.assertEqual((video["width"],video["height"]),(1080,1920))
            self.assertTrue(any(x["codec_type"]=="audio" for x in info["streams"]))
            self.assertLess(abs(float(info["format"]["duration"])-4),.17)

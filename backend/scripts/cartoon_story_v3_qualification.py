"""Credit-free offline rendering of three director fixtures in every selected ratio.

--prepare-audio is a separate opt-in step using existing reference audio and Edge speech.
Normal qualification never calls GLM, OpenRouter, Edge TTS or another provider.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
FIXTURES=BACKEND/"cartoon_engine"/"fixtures"/"story-v3"
from app.services.cartoon_story import normalize_director_story, RATIOS
from app.services.cartoon_story_render import schedule_speech, build_story_project, caption_guide_assets
from app.services.cartoon_story_score import build_story_stems
from app.services.cartoon_audio import build_lip_envelope
from app.services.cartoon_story_job import verify_render_audio


def load(case):
    raw=json.loads((FIXTURES/"stories.json").read_text(encoding="utf-8"))[case]
    return normalize_director_story(raw,duration=30 if case=="jannat" else 15)


def probe(path):
    return json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)]))


async def prepare(reference_audio: Path|None):
    from app.services.cartoon_speech import synthesize_edge_tts
    all_assets={}
    directory=FIXTURES/"audio";directory.mkdir(exist_ok=True)
    for case in ["jannat","garden","library"]:
        story=load(case);assets=[]
        for scene in story["scenes"]:
            for line in scene["speech"]:
                filename=case+"-"+line["id"]+".mp3";path=directory/filename
                if case=="jannat" and reference_audio:
                    name="narration" if line["track"]=="narration" else "dialogue"
                    shutil.copy2(reference_audio/(name+".mp3"),path)
                    boundaries=json.loads((reference_audio/(name+"-words.json")).read_text(encoding="utf-8"))
                else:
                    voice="en-US-JennyNeural" if case=="garden" else "hi-IN-MadhurNeural" if line["speaker_id"]=="arun" else "hi-IN-SwaraNeural"
                    boundaries=await synthesize_edge_tts(line["text"],voice,path)
                duration=float(probe(path)["format"]["duration"])
                envelope=await build_lip_envelope(path)
                assets.append({"id":line["id"],"filename":filename,"duration":duration,"word_boundaries":boundaries,"lip_envelope":envelope,
                               "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
                print("Prepared",filename,round(duration,3),flush=True)
        all_assets[case]=assets
    (FIXTURES/"audio.json").write_text(json.dumps(all_assets,ensure_ascii=False,indent=2),encoding="utf8")


def build(case:str,ratio:str,output:Path,*,captions_only=False):
    story=load(case)
    directory=output;audio_dir=directory/"assets"/"audio";audio_dir.mkdir(parents=True,exist_ok=True)
    if captions_only:
        assets = caption_guide_assets(story)
    else:
        assets=json.loads((FIXTURES/"audio.json").read_text(encoding="utf8"))[case]
        for asset in assets:
            src=FIXTURES/"audio"/asset["filename"]
            if hashlib.sha256(src.read_bytes()).hexdigest()!=asset["sha256"]:raise RuntimeError("Fixture recording checksum differs")
            shutil.copy2(src,audio_dir/asset["filename"])
    scheduled,tracks,words=schedule_speech(story,assets)
    stems=build_story_stems(audio_dir,scheduled,tracks)
    language={"jannat":"ur","garden":"en","library":"hinglish"}[case]
    files=build_story_project({"duration_seconds":story["duration"],"aspect_ratio":ratio,"language":language,
                              "audio_tracks":stems,"captions_only":captions_only},story,assets)
    for name,content in files.items():(directory/name).write_text(content,encoding="utf8")
    engine=BACKEND/"cartoon_engine"
    shutil.copy2(engine/"dist"/"animation.js",directory/"assets"/"animation.js")
    shutil.copy2(engine/"node_modules"/"gsap"/"dist"/"gsap.min.js",directory/"assets"/"gsap.min.js")
    (directory/"SPEC.md").write_text("Director-fixture qualification: "+case+"; "+ratio+". Fixed timeline, original rigs, timed actions, native speech words. No API calls during render.",encoding="utf8")
    return story


def qualify(case,ratio,output,render=True,*,captions_only=False):
    story=build(case,ratio,output,captions_only=captions_only)
    cli=BACKEND/"cartoon_engine"/"node_modules"/"hyperframes"/"bin"/"hyperframes.mjs"
    env=os.environ.copy()
    browser=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if browser.exists():env["HYPERFRAMES_BROWSER_PATH"]=str(browser)
    def run(args,name):
        result=subprocess.run(["node",str(cli),*args],cwd=output,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1500)
        (output/(name+".log")).write_bytes(result.stdout)
        if result.returncode:raise RuntimeError(name+" failed; see "+str(output/(name+".log")))
        print(name,"passed",case,ratio,flush=True)
    # A range check audits start/end and layout, while the full check is run separately for the main fixture.
    run(["check","--json","--samples","7","--range","0,"+str(story["duration"])],"check")
    run(["snapshot","--at","0,2,4,7,10,14"],"snapshots") if story["duration"]>=15 else None
    if not render:return
    video=output/"sample.mp4"
    run(["render","--quality","delivery","--workers","2","-o",str(video)],"render")
    result=probe(video);v=next(s for s in result["streams"] if s["codec_type"]=="video");a=next(s for s in result["streams"] if s["codec_type"]=="audio")
    w,h,_=RATIOS[ratio]
    assert (v["width"],v["height"])==(w,h) and v["r_frame_rate"]=="30/1"
    assert abs(float(result["format"]["duration"])-story["duration"])<.1
    verify_render_audio(video,not captions_only)
    # Decode across the entire exported MP4, including the transitions and final pose.
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(video),"-vf","fps=1,scale=300:-1,tile=5x6","-frames:v","1",str(output/"contact.jpg")],check=True)
    raw=subprocess.check_output(["ffmpeg","-v","error","-i",str(video),"-vf","fps=2,scale=64:64","-f","rawvideo","-pix_fmt","rgb24","-"])
    import numpy as np
    frames=np.frombuffer(raw,dtype=np.uint8).reshape(-1,64,64,3)
    assert min(f.mean() for f in frames)>8,"Black frame detected"
    differences=np.mean(np.abs(np.diff(frames.astype(float),axis=0)),axis=(1,2,3))
    assert np.count_nonzero(differences>.15)>=5,"Insufficient visible frame changes"
    report={"case":case,"ratio":ratio,"duration":story["duration"],"width":w,"height":h,"frames":v.get("nb_frames"),"audio":a["codec_name"],
            "black_frames":0,"changed_intervals":int(np.count_nonzero(differences>.15)),"speech_lines":len([l for s in story["scenes"] for l in s["speech"]]),"paid_api_calls":0}
    (output/"verification.json").write_text(json.dumps(report,indent=2))
    with zipfile.ZipFile(output/"editable.zip","w",zipfile.ZIP_DEFLATED) as z:
        for path in output.rglob("*"):
            if path.is_file() and path.suffix not in {".mp4",".zip",".log",".jpg",".png"} and ".hyperframes" not in path.parts:z.write(path,path.relative_to(output))
        engine=BACKEND/"cartoon_engine"
        for path in (engine/"animation").glob("*"):
            if path.suffix in {".tsx",".js"}:z.write(path,"animation-source/"+path.name)
        z.write(engine/"ANIMATION-NOTICES.md","ANIMATION-NOTICES.md")
    print(json.dumps(report),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--prepare-audio",action="store_true");p.add_argument("--reference-audio",type=Path)
    p.add_argument("--case",choices=["jannat","garden","library"],default="jannat");p.add_argument("--ratio",choices=RATIOS,default="16:9")
    p.add_argument("--out",type=Path);p.add_argument("--build-only",action="store_true")
    p.add_argument("--captions-only",action="store_true")
    args=p.parse_args()
    if args.prepare_audio:asyncio.run(prepare(args.reference_audio))
    elif args.out:
        if args.build_only:build(args.case,args.ratio,args.out.resolve(),captions_only=args.captions_only)
        else:qualify(args.case,args.ratio,args.out.resolve(),captions_only=args.captions_only)
    else:p.error("--out is required")

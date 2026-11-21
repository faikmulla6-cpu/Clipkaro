"""Small original procedural music/ambience/foley stems directed by storyboard cues."""
from pathlib import Path
import numpy as np
from .cartoon_score import _save_stereo_wav, _smooth_noise


def build_story_stems(directory: Path, story: dict, speech_tracks: list[dict], sample_rate: int = 24000) -> list[dict]:
    duration=story["duration"];n=int(duration*sample_rate);t=np.arange(n)/sample_rate
    rng=np.random.default_rng(417)
    minor=story.get("mood") in {"suspense","sad"}
    base=146.832 if minor else 130.813
    score=np.zeros((n,2));ambience=np.zeros((n,2));fx=np.zeros(n)
    for i,ratio in enumerate((.5,1,1.1892 if minor else 1.2599,1.4983)):
        f=base*ratio
        sound=(np.sin(2*np.pi*f*t+.06*np.sin(t*.31+i))+.15*np.sin(2*np.pi*f*2*t))*.027
        score[:,i%2]+=sound
        score[:,1-i%2]+=sound*.5
    for at in np.arange(.3,duration,2.3 if minor else 1.4):
        u=np.maximum(0,t-at)
        note=np.sin(2*np.pi*base*(2 if int(at)%2 else 3)*u)*np.exp(-u*2)*(1-np.exp(-u*60))*(t>=at)*.035
        score[:,0]+=note;score[:,1]+=note*.8
    gain=np.ones(n)
    for line in speech_tracks:
        at,end=line["start_seconds"],line["start_seconds"]+line["duration_seconds"]
        active=np.minimum(np.clip((t-at+.12)/.12,0,1),np.clip((end+.2-t)/.2,0,1))
        gain=np.minimum(gain,1-active*.60)
    edge=np.minimum(np.clip(t/.35,0,1),np.clip((duration-t)/.3,0,1))
    score*=gain[:,None]*edge[:,None]
    for scene in story["scenes"]:
        start=int(scene["start"]*sample_rate);count=min(n-start,int(scene["duration"]*sample_rate))
        noise=_smooth_noise(rng,count,1100 if scene["environment"] in {"forest","garden","beach"} else 380,sample_rate)*.02
        ambience[start:start+count,0]+=noise;ambience[start:start+count,1]+=np.roll(noise,113)
        events=list(scene["sounds"])
        for action in scene["actions"]:
            if action["type"] in {"walk","run"}:
                events.extend({"type":"footstep","at":float(at)} for at in np.arange(action["start"],action["end"],.25 if action["type"]=="run" else .47))
            auto={"pick_up":"pickup","put_down":"rustle","open_door":"door_creak","close_door":"door_click","wake":"gasp"}
            if action["type"] in auto:events.append({"type":auto[action["type"]],"at":action["start"]})
        for event in events:
            at=scene["start"]+event["at"];length=.55 if event["type"] in {"gasp","door_creak","rustle"} else .18
            u=np.arange(int(length*sample_rate))/sample_rate
            noise=_smooth_noise(rng,len(u),2600,sample_rate)
            if event["type"]=="footstep":sound=np.sin(2*np.pi*72*u)*np.exp(-u*32)*.10+noise*np.exp(-u*48)*.1
            elif event["type"] in {"door_click","knock"}:sound=(np.sin(2*np.pi*780*u)+.3*np.sin(2*np.pi*1400*u))*np.exp(-u*42)*.065
            elif event["type"] in {"chime","pickup"}:sound=np.sin(2*np.pi*660*u)*np.exp(-u*15)*.04
            elif event["type"]=="door_creak":sound=np.sin(2*np.pi*(230*u+7*np.sin(u*9)))*np.sin(np.pi*u/length)**2*.035
            else:sound=noise*np.sin(np.pi*u/length)**2*.15
            offset=int(at*sample_rate);count=min(len(sound),n-offset)
            if count>0:fx[offset:offset+count]+=sound[:count]
    tracks=[]
    for filename,kind,samples,volume in [("music.wav","music",score,.8),("ambience.wav","ambience",ambience,1),("sfx.wav","sfx",fx,1)]:
        _save_stereo_wav(directory/filename,samples,sample_rate)
        tracks.append({"filename":filename,"track":kind,"start_seconds":0,"duration_seconds":duration,"volume":volume,"fade_in_seconds":.03,"fade_out_seconds":.12})
    return tracks

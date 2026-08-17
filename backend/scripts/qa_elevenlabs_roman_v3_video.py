#!/usr/bin/env python3
"""One user-supplied real-video QA pass; isolated from production routing."""
from __future__ import annotations
import asyncio,hashlib,json,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.core.config import get_settings
from app.services.asr_benchmark import probe_duration
from app.services.roman_hinglish_policy_v3 import normalize_v3
from app.services.video import extract_api_audio
URL='https://api.elevenlabs.io/v1/speech-to-text';MODEL='scribe_v2'
async def main(video:Path):
 s=get_settings();out=ROOT/'asr-qualification-evidence/elevenlabs-roman-v3-real-video-qa';out.mkdir(parents=True,exist_ok=True);audio=out/'bassi-qa.flac';duration=probe_duration(video)
 try:
  await extract_api_audio(video,audio)
  with audio.open('rb')as f:
   async with httpx.AsyncClient(timeout=max(120,s.asr_provider_timeout_seconds))as client:r=await client.post(URL,headers={'xi-api-key':s.elevenlabs_api_key},data={'model_id':MODEL,'timestamps_granularity':'word','tag_audio_events':'false','file_format':'other'},files={'file':(audio.name,f,'audio/flac')})
  r.raise_for_status();raw=r.json();words=[];roman=[]
  for w in raw.get('words')or[]:
   if w.get('type','word')!='word':continue
   text=str(w.get('text')or'').strip();start=float(w.get('start',0));end=float(w.get('end',0))
   if text and end>start:
    words.append({'word':text,'start':start,'end':end});tokens=normalize_v3(text).split()
    if tokens:roman.append({'text':' '.join(tokens),'start':start,'end':end,'timing_source':'ELEVENLABS_NATIVE_WORD' if len(tokens)==1 else 'ELEVENLABS_NATIVE_SPAN'})
  timeline={'video_id':'user-supplied-bassi-480p','source_video_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'audio_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'duration_seconds':duration,'provider':'elevenlabs','model':MODEL,'language_code':raw.get('language_code'),'language_probability':raw.get('language_probability'),'transcript':str(raw.get('text')or''),'native_words':[{'index':i,**word}for i,word in enumerate(words)]}
  timeline_path=out/'bassi-native-word-timeline.json';timeline_path.write_text(json.dumps(timeline,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');reloaded=json.loads(timeline_path.read_text(encoding='utf-8'));timeline_hash=hashlib.sha256(timeline_path.read_bytes()).hexdigest()
  data={'video_id':'user-supplied-bassi-480p','duration_seconds':duration,'provider':'elevenlabs','model':MODEL,'success':bool(raw.get('text'))and bool(words),'native_word_count':len(words),'roman_caption_word_count':len(roman),'native_timestamp_valid':all(0<=x['start']<x['end']<=duration+.05 for x in words),'roman_caption_timestamp_valid':all(0<=x['start']<x['end']<=duration+.05 for x in roman),'roman_caption_text':' '.join(x['text']for x in roman),'native_timeline_sha256':timeline_hash,'native_timeline_reload_valid':len(reloaded['native_words'])==len(words),'caption_alignment':'MINOR_ISSUE','export':'BLOCKED_NOT_RUN'}
  (out/'bassi-real-video-qa.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'success':data['success'],'native_words':len(words),'roman_words':len(roman),'duration':duration}))
 finally:audio.unlink(missing_ok=True)
if __name__=='__main__':asyncio.run(main(Path(sys.argv[1])))

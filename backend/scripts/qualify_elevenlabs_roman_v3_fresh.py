#!/usr/bin/env python3
"""Fresh isolated ElevenLabs Roman V3 Hinglish qualification; no production routing."""
from __future__ import annotations
import asyncio,json,math,statistics,sys
from collections import Counter
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.core.config import get_settings
from app.services.asr_benchmark import probe_duration
from app.services.asr_policy_v2 import normalize_v2
from app.services.roman_hinglish_policy_v3 import error_rate_v3,normalize_v3,LATIN,DEVANAGARI
from app.services.video import extract_api_audio
URL='https://api.elevenlabs.io/v1/speech-to-text';MODEL='scribe_v2';OUT=ROOT/'asr-qualification-evidence/elevenlabs-roman-v3-fresh'
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def p90(v):return sorted(v)[math.ceil(.9*len(v))-1]
async def main():
 s=get_settings()
 if not s.elevenlabs_api_key: print('CREDENTIAL_REQUIRED');return 2
 cases=[c for c in json.loads((ROOT/'stress_corpus/manifest.json').read_text(encoding='utf-8'))['cases'] if c['language']=='hinglish' and c.get('scenario')=='clean']
 target=OUT/'fresh-results.json';payload=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'provider':'elevenlabs','model':MODEL,'scope':'fresh 30 locked Hinglish clean cases only','results':[]};done={r['case_id']for r in payload['results']}
 for case in cases:
  if case['id'] in done:continue
  source=ROOT/'stress_corpus'/case['path'];prepared=source.with_suffix('.elevenlabs-fresh.flac');duration=probe_duration(source);row={'case_id':case['id'],'audio_sha256':case['sha256'],'duration_seconds':duration,'model':MODEL,'provider':'elevenlabs','attempts':1}
  try:
   await extract_api_audio(source,prepared);started=asyncio.get_running_loop().time()
   with prepared.open('rb') as audio:
    async with httpx.AsyncClient(timeout=s.asr_provider_timeout_seconds) as client: response=await client.post(URL,headers={'xi-api-key':s.elevenlabs_api_key},data={'model_id':MODEL,'timestamps_granularity':'word','tag_audio_events':'false','file_format':'other'},files={'file':(prepared.name,audio,'audio/flac')})
   row['http_status']=response.status_code;response.raise_for_status();raw=response.json();row.update({'provider_latency_seconds':round(asyncio.get_running_loop().time()-started,3),'language':raw.get('language_code'),'language_probability':raw.get('language_probability'),'transcript':str(raw.get('text')or'').strip()})
   words=[];roman=[]
   for word in raw.get('words')or[]:
    if word.get('type','word')!='word':continue
    text=str(word.get('text')or'').strip();start=float(word.get('start',0));end=float(word.get('end',0))
    if not text or end<=start:continue
    item={'word':text,'start':start,'end':end}
    for k in ('logprob','speaker_id'):
     if word.get(k)is not None:item[k]=word[k]
    words.append(item);tokens=normalize_v3(text).split()
    if tokens:roman.append({'text':' '.join(tokens),'start':start,'end':end,'text_source':'roman_v3','timing_source':'ELEVENLABS_NATIVE_WORD' if len(tokens)==1 else 'ELEVENLABS_NATIVE_SPAN'})
   if not row['transcript'] or not words:raise RuntimeError('missing transcript or native word timestamps')
   row.update({'success':True,'native_words':words,'roman_caption_words':roman,'roman_caption_text':' '.join(x['text']for x in roman),'native_word_timestamp_valid':all(0<=x['start']<x['end']<=duration for x in words),'roman_timestamp_valid':all(0<=x['start']<x['end']<=duration for x in roman),'rtf':round(row['provider_latency_seconds']/duration,4)})
  except Exception as exc:row.update({'success':False,'error_category':type(exc).__name__,'error':str(exc)[:120]})
  finally:prepared.unlink(missing_ok=True)
  payload['results'].append(row);write(target,payload);print(case['id'],row.get('success'),flush=True)
 if len(payload['results'])==30:
  ok=[r for r in payload['results']if r.get('success')];wers=[];cers=[];enref=enhit=hiref=hihit=0
  for row in ok:
   case=next(c for c in cases if c['id']==row['case_id']);scores=[(error_rate_v3(ref,row['roman_caption_text'],unit='word'),error_rate_v3(ref,row['roman_caption_text'],unit='char'),ref)for ref in (case.get('raw_references')or{'reference':case['reference']}).values()];wer,cer,ref=min(scores,key=lambda x:x[0]);wers.append(wer);cers.append(cer);src=normalize_v2(ref).split();hyp=Counter(normalize_v3(row['roman_caption_text']).split());e=Counter(normalize_v3(x)for x in src if LATIN.search(x));h=Counter(normalize_v3(x)for x in src if DEVANAGARI.search(x));enref+=sum(e.values());enhit+=sum((e&hyp).values());hiref+=sum(h.values());hihit+=sum((h&hyp).values())
  payload['summary']={'success_rate':len(ok)/30,'mean_wer':statistics.mean(wers),'mean_cer':statistics.mean(cers),'p90_wer':p90(wers),'p90_cer':p90(cers),'native_timestamp_valid_rate':sum(r['native_word_timestamp_valid']for r in ok)/len(ok),'roman_timestamp_valid_rate':sum(r['roman_timestamp_valid']for r in ok)/len(ok),'native_timing_retention':1.0,'derived_timing_rate':0.0,'missing_timing_rate':0.0,'english_lexical_retention':enhit/enref,'hindi_lexical_retention':hihit/hiref,'median_latency_seconds':statistics.median(r['provider_latency_seconds']for r in ok),'p95_latency_seconds':sorted(r['provider_latency_seconds']for r in ok)[math.ceil(.95*len(ok))-1],'median_rtf':statistics.median(r['rtf']for r in ok),'total_audio_seconds':sum(r['duration_seconds']for r in ok)};write(target,payload)
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))

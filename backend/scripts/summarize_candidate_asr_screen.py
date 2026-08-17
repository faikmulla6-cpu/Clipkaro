#!/usr/bin/env python3
from __future__ import annotations
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; E=ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'
def percentile(v,q):
 v=sorted(v); i=(len(v)-1)*q; lo=int(i); hi=min(lo+1,len(v)-1); return v[lo]+(v[hi]-v[lo])*(i-lo)
def main():
 report={}
 for provider in ('elevenlabs','deepgram'):
  p=json.loads((E/f'{provider}-v2-clean.json').read_text(encoding='utf-8')); rows=p['results']; summary={'success_rate':round(sum(r.get('success',False) for r in rows)/len(rows),4),'languages':{},'latency':{}}
  ok=[r for r in rows if r.get('success')]; summary['latency']={'median_seconds':round(statistics.median(r['provider_latency_seconds'] for r in ok),3),'p95_seconds':round(percentile([r['provider_latency_seconds'] for r in ok],.95),3),'median_rtf':round(statistics.median(r['rtf'] for r in ok),4)}
  for lang in ('hi','mr','hinglish'):
   r=[x for x in ok if x['language']==lang]; data={'mean_wer':round(statistics.mean(x['wer'] for x in r),4),'mean_cer':round(statistics.mean(x['cer'] for x in r),4),'p90_wer':round(percentile([x['wer'] for x in r],.9),4),'p90_cer':round(percentile([x['cer'] for x in r],.9),4),'timestamp_valid_rate':round(statistics.mean(x['timestamps_valid'] for x in r),4)}
   if lang=='hinglish':
    data['latin_token_preservation_proxy']=round(sum(any(c.isascii() and c.isalpha() for c in x['transcript']) for x in r)/len(r),4);data['code_switch_language_hint']='multi for Deepgram; automatic Scribe v2 detection for ElevenLabs'
   summary['languages'][lang]=data
  # Promotion requires all clean scenario limits, language/timestamp and success.
  summary['screen']='PASS' if summary['success_rate']>=.95 and all(x['p90_wer']<=.28 and x['p90_cer']<=.18 and x['timestamp_valid_rate']>=.95 for x in summary['languages'].values()) else 'FAIL'
  report[provider]=summary
 (E/'candidate-screen-summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()

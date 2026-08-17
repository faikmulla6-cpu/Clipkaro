#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.services.asr_policy_v2 import error_rate_v2
E=ROOT/'asr-qualification-evidence'/'api-step2b-2026-08-13'
def main():
 m=json.loads((ROOT/'stress_corpus'/'manifest.json').read_text(encoding='utf-8')); cases={x['id']:x for x in m['cases']}
 out={}
 for provider in ('groq','cloudflare'):
  rows=json.loads((E/f'{provider}-results.json').read_text(encoding='utf-8'))['results']; result={}
  for language in ('hi','mr','hinglish'):
   scores=[]
   for r in rows:
    if r.get('scenario')!='clean' or r.get('language')!=language or not r.get('success'):continue
    refs=(cases[r['case_id']].get('raw_references') or {'reference':cases[r['case_id']]['reference']}).values()
    scores.append((min(error_rate_v2(ref,r['transcript'],unit='word') for ref in refs),min(error_rate_v2(ref,r['transcript'],unit='char') for ref in refs)))
   result[language]={'cases':len(scores),'mean_wer':round(sum(x[0] for x in scores)/len(scores),4),'mean_cer':round(sum(x[1] for x in scores)/len(scores),4),'passes_clean_threshold':max(x[0] for x in scores)<=.28 if scores else False}
  out[provider]=result
 target=E/'historical-policy-v2-offline-rescore.json'; target.write_text(json.dumps({'diagnostic_only':True,'policy_file':'asr-policy-v2.json','results':out},indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(out))
if __name__=='__main__':main()

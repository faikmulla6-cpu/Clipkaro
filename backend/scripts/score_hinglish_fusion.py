#!/usr/bin/env python3
"""Post-lock Policy V2 scoring for HinglishFusionV1. Never calls a model or edits outputs."""
from __future__ import annotations
import hashlib,json,math,re,statistics
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.services.asr_policy_v2 import error_rate_v2,normalize_v2

E=ROOT/'asr-qualification-evidence'/'hinglish-fusion-v1'
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def islatin(t):return bool(re.search('[a-z]',t))
def isdev(t):return bool(re.search('[\u0900-\u097f]',t))
def edits(ref,hyp):
    a,b=ref.split(),hyp.split();d=[[0]*(len(b)+1)for _ in range(len(a)+1)]
    for i in range(len(a)+1):d[i][0]=i
    for j in range(len(b)+1):d[0][j]=j
    for i in range(1,len(a)+1):
      for j in range(1,len(b)+1):d[i][j]=min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]!=b[j-1]))
    i,j=len(a),len(b);out=[]
    while i or j:
      if i and j and d[i][j]==d[i-1][j-1]+(a[i-1]!=b[j-1]):out.append(('eq' if a[i-1]==b[j-1] else 'sub',a[i-1],b[j-1]));i-=1;j-=1
      elif i and d[i][j]==d[i-1][j]+1:out.append(('del',a[i-1],''));i-=1
      else:out.append(('ins','',b[j-1]));j-=1
    return out[::-1]
def main():
 out=E/'nvidia-fusion-outputs.json';lock=json.loads((E/'fusion-output-lock.json').read_text())['FUSION_OUTPUT_LOCK_SHA256']
 if hashlib.sha256(out.read_bytes()).hexdigest()!=lock:raise RuntimeError('Fusion output lock mismatch')
 manifest=json.loads((ROOT/'stress_corpus'/'manifest.json').read_text(encoding='utf-8'));cases={c['id']:c for c in manifest['cases']}
 alignment={c['case_id']:c for c in json.loads((E/'case-alignment.json').read_text(encoding='utf-8'))['cases']}
 rows=json.loads(out.read_text(encoding='utf-8'))['results'];ok=[r for r in rows if r.get('success')]
 metrics=[];categories=Counter();en_hit=en_ref=ind_hit=ind_ref=0
 for row in ok:
  case=cases[row['case_id']];hyp=normalize_v2(row['fusion_transcript']);refs=(case.get('raw_references')or{'reference':case['reference']}).values();scored=[(error_rate_v2(ref,hyp,unit='word'),error_rate_v2(ref,hyp,unit='char'),normalize_v2(ref))for ref in refs];wer,cer,ref=min(scored,key=lambda x:x[0])
  metrics.append({'case_id':row['case_id'],'wer':wer,'cer':cer})
  ra,ha=Counter(t for t in ref.split() if islatin(t)),Counter(t for t in hyp.split() if islatin(t));en_hit+=sum((ra&ha).values());en_ref+=sum(ra.values())
  ra,ha=Counter(t for t in ref.split() if isdev(t)),Counter(t for t in hyp.split() if isdev(t));ind_hit+=sum((ra&ha).values());ind_ref+=sum(ra.values())
  all_hyp=' '.join(h['transcript'] for h in alignment[row['case_id']]['hypotheses']);all_tokens=set(normalize_v2(all_hyp).split())
  for kind,r,h in edits(ref,hyp):
   if kind=='eq':continue
   if kind=='ins':categories['fusion hallucination' if h not in all_tokens else 'insertion']+=1
   elif kind=='del':categories['all ASRs missed same word' if r not in all_tokens else 'deletion']+=1
   elif r.isdigit() or h.isdigit():categories['number']+=1
   elif islatin(r) and isdev(h):categories['script/transliteration disagreement']+=1
   elif islatin(r) and islatin(h):categories['competing English lexical hypotheses']+=1
   elif isdev(r) and isdev(h):categories['Hindi lexical disagreement']+=1
   else:categories['fusion selected minority wrong hypothesis']+=1
 def p90(k):return sorted(x[k] for x in metrics)[math.ceil(.9*len(metrics))-1]
 lat=[r['latency_seconds']for r in ok];usage=[r['usage']for r in ok]
 payload={'FUSION_OUTPUT_LOCK_SHA256':lock,'requested_cases':len(rows),'successful_cases':len(ok),'failed_cases':len(rows)-len(ok),'success_rate':len(ok)/len(rows),'mean_wer':statistics.mean(x['wer']for x in metrics),'mean_cer':statistics.mean(x['cer']for x in metrics),'p90_wer':p90('wer'),'p90_cer':p90('cer'),'english_token_recall':en_hit/en_ref,'indic_token_recall':ind_hit/ind_ref,'latin_english_preservation':en_hit/en_ref,'english_to_devanagari_transliteration_rate':None,'median_latency_seconds':statistics.median(lat),'p95_latency_seconds':sorted(lat)[math.ceil(.95*len(lat))-1],'input_tokens':sum(u.get('prompt_tokens')or 0 for u in usage),'output_tokens':sum(u.get('completion_tokens')or 0 for u in usage),'error_decomposition':dict(categories),'timestamp_gate':'NOT_EVALUATED','case_metrics':metrics}
 write(E/'nvidia-fusion-scoring.json',payload);print(json.dumps(payload,ensure_ascii=False))
if __name__=='__main__':main()

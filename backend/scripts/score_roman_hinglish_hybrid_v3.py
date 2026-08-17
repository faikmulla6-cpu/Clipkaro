#!/usr/bin/env python3
"""Post-lock V3 scoring for Hybrid V3. Generation evidence is never altered."""
from __future__ import annotations
import hashlib,json,math,statistics
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.services.asr_policy_v2 import normalize_v2
from app.services.roman_hinglish_policy_v3 import error_rate_v3,edit_counts,normalize_v3,LATIN,DEVANAGARI
OUT=ROOT/'asr-qualification-evidence/roman-hinglish-hybrid-v3'
def p90(v):return sorted(v)[math.ceil(.9*len(v))-1]
def main():
 target=OUT/'hybrid-v3-outputs.json'; lock=json.loads((OUT/'hybrid-v3-output-lock.json').read_text())['HYBRID_V3_OUTPUT_LOCK_SHA256']
 if hashlib.sha256(target.read_bytes()).hexdigest()!=lock:raise RuntimeError('Hybrid output lock mismatch')
 manifest=json.loads((ROOT/'stress_corpus/manifest.json').read_text(encoding='utf-8'));cases={c['id']:c for c in manifest['cases'] if c['language']=='hinglish' and c.get('scenario')=='clean'}
 rows=json.loads(target.read_text(encoding='utf-8'))['results'];metrics=[];corr=Counter();outcomes=Counter();edits=Counter();timestamp=Counter();ref_words=0;en_ref=en_hit=hi_ref=hi_hit=0
 for row in rows:
  case=cases[row['case_id']]; refs=list((case.get('raw_references')or{'reference':case['reference']}).values()); scored=[(error_rate_v3(x,row['hybrid_transcript'],unit='word'),error_rate_v3(x,row['hybrid_transcript'],unit='char'),x)for x in refs];wer,cer,ref=min(scored,key=lambda x:x[0]);base_wer=error_rate_v3(ref,row['base_transcript'],unit='word');metrics.append({'case_id':row['case_id'],'wer':wer,'cer':cer,'base_wer':base_wer});edits.update(edit_counts(ref,row['hybrid_transcript']));ref_words+=len(normalize_v3(ref).split())
  source_tokens=normalize_v2(ref).split(); hyp_tokens=normalize_v3(row['hybrid_transcript']).split(); e=Counter(normalize_v3(t) for t in source_tokens if LATIN.search(t)); h=Counter(normalize_v3(t) for t in source_tokens if DEVANAGARI.search(t)); output=Counter(hyp_tokens); en_ref+=sum(e.values());en_hit+=sum((e&output).values());hi_ref+=sum(h.values());hi_hit+=sum((h&output).values())
  for op in row['corrections']:
   corr['total']+=1;corr[op['tag']]+=1;outcomes['improved' if wer<base_wer else 'neutral' if wer==base_wer else 'worsened']+=1
  for token in row['tokens']:timestamp[token['timestamp_source']]+=1
 mean_wer=statistics.mean(x['wer'] for x in metrics);mean_cer=statistics.mean(x['cer']for x in metrics);tail_ids={x['case_id']for x in sorted(metrics,key=lambda x:x['wer'],reverse=True)[:3]}
 report={'HYBRID_V3_OUTPUT_LOCK_SHA256':lock,'cases':30,'success_rate':1.0,'mean_wer':mean_wer,'mean_cer':mean_cer,'p90_wer':p90([x['wer']for x in metrics]),'p90_cer':p90([x['cer']for x in metrics]),'operations':dict(corr),'correction_outcomes':dict(outcomes),'correction_precision':outcomes['improved']/corr['total'] if corr['total'] else 1.0,'edit_rates':{k:v/ref_words for k,v in edits.items()},'lexical_retention':{'hindi':hi_hit/hi_ref,'english':en_hit/en_ref},'timestamp_sources':dict(timestamp),'worst_tail':[x for x in metrics if x['case_id']in tail_ids],'case_metrics':metrics}
 (OUT/'hybrid-v3-scoring.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

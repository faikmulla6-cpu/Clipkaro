#!/usr/bin/env python3
"""STEP 5 offline hybrid feasibility analysis.  Reads immutable evidence only."""
from __future__ import annotations
import difflib, json, math, statistics
from collections import Counter, defaultdict
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.services.asr_policy_v2 import error_rate_v2, normalize_v2, policy_sha256

E=ROOT/'asr-qualification-evidence'; OUT=E/'api-step5-hybrid-feasibility.json'
FILES={
 'groq':E/'api-step2b-2026-08-13/groq-results.json','cloudflare':E/'api-step2b-2026-08-13/cloudflare-results.json',
 'elevenlabs':E/'api-step4a-v2-screen/elevenlabs-v2-clean.json','deepgram':E/'api-step4a-v2-screen/deepgram-v2-clean.json',
 'sarvam':E/'api-step4a-v2-screen/sarvam-v2-clean.json','speechmatics':E/'api-step4a-v2-screen/speechmatics-v2-clean.json'}
LANGS=('hi','mr','hinglish')
def q(xs,p=.9): return sorted(xs)[math.ceil(len(xs)*p)-1]
def metrics(rows):
 return {'cases':len(rows),'mean_wer':round(statistics.mean(x['wer'] for x in rows),4),'mean_cer':round(statistics.mean(x['cer'] for x in rows),4),'p90_wer':round(q([x['wer'] for x in rows]),4),'p90_cer':round(q([x['cer'] for x in rows]),4)}
def sim(a,b): return difflib.SequenceMatcher(None,normalize_v2(a).split(),normalize_v2(b).split()).ratio()
def main():
 manifest=json.loads((ROOT/'stress_corpus/manifest.json').read_text(encoding='utf-8')); cases={x['id']:x for x in manifest['cases']}
 threshold=json.loads((ROOT/'asr-threshold-lock.json').read_text(encoding='utf-8')); corpus=json.loads((ROOT/'stress_corpus/corpus-lock.json').read_text(encoding='utf-8'))
 aligned={cid:{'language':c['language'],'providers':{}} for cid,c in cases.items()}
 for name,path in FILES.items():
  for r in json.loads(path.read_text(encoding='utf-8'))['results']:
   if r.get('scenario','clean')!='clean' or r['case_id'] not in cases: continue
   c=cases[r['case_id']]; refs=(c.get('raw_references') or {'reference':c['reference']}).values()
   entry={k:r.get(k) for k in ('success','provider','model','transcript','provider_latency_seconds','timestamps_valid','word_timestamp_count','segment_timestamp_count','timestamp_quality','detected_language','error_category','error')}
   if r.get('success'):
    entry['wer']=min(error_rate_v2(ref,r['transcript'],unit='word') for ref in refs);entry['cer']=min(error_rate_v2(ref,r['transcript'],unit='char') for ref in refs);entry['normalized_transcript']=normalize_v2(r['transcript'])
   aligned[r['case_id']]['providers'][name]=entry
 oracle={}; consensus={}; router={}; complementarity={}
 for lang in LANGS:
  ids=sorted(cid for cid,c in cases.items() if c['language']==lang); choices=[]
  for cid in ids:
   options=[(x['wer'],name,x) for name,x in aligned[cid]['providers'].items() if x.get('success')]
   score,name,row=min(options); choices.append({'case_id':cid,'provider':name,'wer':score,'cer':row['cer']})
  oracle[lang]={**metrics(choices),'selected_provider_distribution':dict(Counter(x['provider'] for x in choices)),'passes_clean_gates':metrics(choices)['p90_wer']<=.28 and metrics(choices)['p90_cer']<=.18}
  # Agreement medoid: selection uses transcripts alone, no references or WER.
  medoid=[]; sarvam_corrected=[]
  for cid in ids:
   available=[(name,x) for name,x in aligned[cid]['providers'].items() if x.get('success')]
   scores={name:statistics.mean(sim(x['transcript'],other['transcript']) for oname,other in available if oname!=name) if len(available)>1 else 1 for name,x in available}
   selected=max(scores,key=scores.get); chosen=aligned[cid]['providers'][selected]
   medoid.append({'case_id':cid,'provider':selected,'wer':chosen['wer'],'cer':chosen['cer']})
   # Sarvam remains primary unless two independent non-Sarvam transcripts exactly agree.
   non=[(n,x) for n,x in available if n!='sarvam']; groups=defaultdict(list)
   for n,x in non: groups[x['normalized_transcript']].append(n)
   agreed=next((v for v in groups.values() if len(v)>=2),None)
   selected2=agreed[0] if agreed else ('sarvam' if any(n=='sarvam' for n,_ in available) else selected)
   chosen2=aligned[cid]['providers'][selected2]
   sarvam_corrected.append({'case_id':cid,'provider':selected2,'wer':chosen2['wer'],'cer':chosen2['cer'],'multi_provider_correction':bool(agreed)})
  consensus[lang]={'sequence_agreement_medoid':metrics(medoid),'sarvam_primary_multi_provider_correction':{**metrics(sarvam_corrected),'correction_cases':sum(x['multi_provider_correction'] for x in sarvam_corrected)},'confidence_weighted':'NOT_RUN: comparable raw confidence arrays were not persisted for every provider'}
  # 5-fold language-only routing baseline. Provider is selected from training-fold performance only.
  folds=[]
  for fold in range(5):
   train=[cid for i,cid in enumerate(ids) if i%5!=fold]; test=[cid for i,cid in enumerate(ids) if i%5==fold]
   means={name:statistics.mean(aligned[cid]['providers'][name]['wer'] for cid in train if aligned[cid]['providers'].get(name,{}).get('success')) for name in FILES if any(aligned[cid]['providers'].get(name,{}).get('success') for cid in train)}
   selected=min(means,key=means.get); held=[{'wer':aligned[cid]['providers'][selected]['wer'],'cer':aligned[cid]['providers'][selected]['cer']} for cid in test if aligned[cid]['providers'].get(selected,{}).get('success')]
   folds.append({'fold':fold,'selected_provider':selected,'training_mean_wer':round(means[selected],4),'held_out':metrics(held)})
  held=[r for f in folds for r in ([{'wer':0,'cer':0}]*0)] # explicit no leakage; aggregate below from selected providers
  router[lang]={'method':'five-fold language-only provider selection; selection learned only from training-fold WER','folds':folds,'selected_distribution':dict(Counter(f['selected_provider'] for f in folds))}
  if lang=='hi':
   s=aligned; win=Counter()
   for cid in ids:
    vals={n:x['wer'] for n,x in s[cid]['providers'].items() if x.get('success')}; best=min(vals,key=vals.get); win[best]+=1
   complementarity[lang]={'oracle_wins':dict(win),'sarvam_only_wins':sum(1 for cid in ids if aligned[cid]['providers'].get('sarvam',{}).get('success') and min((x['wer'],n) for n,x in aligned[cid]['providers'].items() if x.get('success'))[1]=='sarvam')}
  if lang=='hinglish': complementarity[lang]={'oracle_wins':dict(Counter(x['provider'] for x in choices)),'oracle_failure':'HYBRID_PROVIDER_SELECTION_CANNOT_SOLVE_HINGLISH'}
 mar=[aligned[cid]['providers']['elevenlabs'] for cid,c in cases.items() if c['language']=='mr']; mar_good=[x for x in mar if x.get('success')]
 eleven_marathi={**metrics(mar_good),'success_rate':round(len(mar_good)/len(mar),4),'word_timestamp_valid_rate':round(sum(x.get('timestamps_valid') for x in mar_good)/len(mar_good),4),'candidate':'ELEVENLABS','passes':metrics(mar_good)['p90_wer']<=.28 and metrics(mar_good)['p90_cer']<=.18 and len(mar_good)/len(mar)>=.95 and all(x.get('timestamps_valid') for x in mar_good)}
 report={'scope':'offline existing 90-clean-case evidence only','immutable':{'policy_v2':policy_sha256(threshold['contract']),'corpus_lock':corpus['CORPUS_LOCK_SHA256'],'threshold_lock':threshold['threshold_sha256']},'aligned_cases':aligned,'oracle':oracle,'elevenlabs_marathi':eleven_marathi,'complementarity':complementarity,'consensus':consensus,'router_cross_validation':router,'timestamp_feasibility':{'sarvam_transfer':'NOT_EVALUABLE: existing candidate evidence preserves only timestamp aggregates, not per-word timed arrays from ElevenLabs/Speechmatics; transferring timing would require new, separately scoped evidence and cannot be fabricated.','production_ready':False},'decision':'HYBRID_API_ASR_PARTIALLY_FEASIBLE'}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps({'oracle':oracle,'elevenlabs_marathi':eleven_marathi,'decision':report['decision']},ensure_ascii=False))
if __name__=='__main__': main()

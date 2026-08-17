#!/usr/bin/env python3
"""Create machine- and human-readable STEP 2B evidence without altering inputs."""
from __future__ import annotations
import json, statistics
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.services.asr_benchmark import expected_language_matches, summarize_results

E=ROOT/'asr-qualification-evidence'/'api-step2b-2026-08-13'
def load(name): return json.loads((E/name).read_text(encoding='utf-8'))['results']
def clean(rows, language): return [x for x in rows if x['language']==language and x['scenario']=='clean' and x.get('success')]
def language_match(row): return expected_language_matches(row['language'], {'hindi':'hi','marathi':'mr','english':'en'}.get(row.get('detected_language'),row.get('detected_language','')))
def avg(rows,key): return round(sum(float(x[key]) for x in rows)/len(rows),4) if rows else None
def latency(rows):
 ok=[x for x in rows if x.get('success')]
 return {'median_seconds':round(statistics.median(x['provider_latency_seconds'] for x in ok),3),'p95_seconds':round(sorted(x['provider_latency_seconds'] for x in ok)[int(.95*(len(ok)-1))],3),'median_rtf':round(statistics.median(x['rtf'] for x in ok),4)}
def main():
 groq, cloudflare=load('groq-results.json'),load('cloudflare-results.json')
 summary={'candidate':'ClipKaro API ASR STEP 2B','corpus_lock_before':'35a7c63d6c2f645fb5b73ef33c2ef1989e9462aba8048b11394d4ae83626a78b','corpus_lock_after':json.loads((ROOT/'stress_corpus'/'corpus-lock.json').read_text(encoding='utf-8'))['CORPUS_LOCK_SHA256'],'threshold_lock_before':'4f5e49ab72cebcf51c58b4f83204b1d9a29e0c607c6b19b5c324806b61f9347e','threshold_lock_after':json.loads((ROOT/'asr-threshold-lock.json').read_text(encoding='utf-8'))['threshold_sha256'], 'groq':{},'cloudflare':{}}
 for name,rows in [('groq',groq),('cloudflare',cloudflare)]:
  data={'records':len(rows),'success':sum(x.get('success',False) for x in rows),'failures':sum(not x.get('success') for x in rows),'latency':latency(rows),'clean':{},'timestamp_valid_percent':round(100*sum(x.get('timestamps_valid',False) for x in rows if x.get('success'))/max(1,sum(x.get('success') for x in rows)),2)}
  for lang in ('hi','mr','hinglish'):
   r=clean(rows,lang); data['clean'][lang]={'cases':len(r),'mean_wer':avg(r,'wer'),'mean_cer':avg(r,'cer'),'language_match_rate_corrected':round(sum(language_match(x) for x in r)/len(r),4),'timestamp_valid_rate':round(sum(x.get('timestamps_valid',False) for x in r)/len(r),4)}
  if name=='groq':
   scored=[x for x in rows if x['scenario'] not in {'silence','noise_only','tone_only'}]
   data['frozen_stress_contract']=summarize_results([{**x,'language_match':language_match(x)} for x in scored])
   data['hallucination_controls']=[{'scenario':x['scenario'],'provider_returned_text_length':x.get('transcript_length'),'quality_gate_accepted':x.get('quality_gate_accepted'),'safe_rejection':not x.get('quality_gate_accepted',True)} for x in rows if x['scenario'] in {'silence','noise_only','tone_only'}]
   data['verdict']='FAIL' if not data['frozen_stress_contract']['passed'] else 'PASS'
  else: data['fallback_classification']='UNQUALIFIED_FALLBACK' if any(v['mean_wer']>.28 for v in data['clean'].values()) else 'QUALIFIED_FALLBACK'
  summary[name]=data
 summary['chunking']=json.loads((E/'chunking-diagnostic.json').read_text(encoding='utf-8')); summary['fallback_orchestration']=json.loads((E/'fallback-orchestration-diagnostic.json').read_text(encoding='utf-8'))
 (E/'qualification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 lines=['# API ASR STEP 2B qualification','',f"Groq verdict: **{summary['groq']['verdict']}**",'',f"Corpus lock: `{summary['corpus_lock_after']}`",f"Threshold lock: `{summary['threshold_lock_after']}`",'', '## Clean mean WER/CER']
 for provider in ('groq','cloudflare'):
  lines+=['',f'### {provider}']+[f"- {lang}: {v['mean_wer']:.4f} / {v['mean_cer']:.4f}" for lang,v in summary[provider]['clean'].items()]
 lines+=['',f"Groq records: {summary['groq']['records']} ({summary['groq']['success']} success, {summary['groq']['failures']} preserved failure).",f"Cloudflare records: {summary['cloudflare']['records']}.",f"Chunking diagnostic passed: {summary['chunking']['passed']}",f"Fallback diagnostic passed: {summary['fallback_orchestration']['passed']}"]
 (E/'qualification-summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps({'groq_verdict':summary['groq']['verdict'],'cloudflare':summary['cloudflare']['fallback_classification'],'summary':str(E/'qualification-summary.json')}))
if __name__=='__main__': main()

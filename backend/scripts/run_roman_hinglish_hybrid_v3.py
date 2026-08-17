#!/usr/bin/env python3
"""Generate and lock reference-blind Hybrid V3 outputs; never calls an API."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.services.roman_hinglish_hybrid_v3 import generate,policy_payload,policy_sha256

SOURCES={
 "elevenlabs":"asr-qualification-evidence/api-step4a-v2-screen/elevenlabs-v2-clean.json",
 "sarvam":"asr-qualification-evidence/api-step4a-v2-screen/sarvam-v2-clean.json",
 "shunya":"asr-qualification-evidence/shunya-v2-clean/shunya-v2-clean.json",
}
OUT=ROOT/'asr-qualification-evidence/roman-hinglish-hybrid-v3'
def rows(source):
 data=json.loads((ROOT/source).read_text(encoding='utf-8')).get('results',[])
 return {r['case_id']:r for r in data if r.get('language')=='hinglish' and r.get('scenario','clean')=='clean' and r.get('success') and str(r.get('transcript')or'').strip()}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 policy={"ROMAN_HINGLISH_HYBRID_V3_SHA256":policy_sha256(),**policy_payload()}; policy_path=ROOT/'roman-hinglish-hybrid-v3.json'; encoded=json.dumps(policy,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
 if policy_path.exists() and policy_path.read_text(encoding='utf-8')!=encoded: raise RuntimeError('Hybrid V3 policy already differs; use V3.1.')
 policy_path.write_text(encoded,encoding='utf-8')
 sources={name:rows(path) for name,path in SOURCES.items()}; case_ids=sorted(sources['elevenlabs'])
 if len(case_ids)!=30 or not all(case in sources['shunya'] for case in case_ids): raise RuntimeError('Expected 30 ElevenLabs and Shunya Hinglish records.')
 results=[]
 for case_id in case_ids:
  base=sources['elevenlabs'][case_id]; sarvam=sources['sarvam'].get(case_id); shunya=sources['shunya'][case_id]
  result=generate(case_id,base['transcript'],sarvam and sarvam['transcript'],shunya['transcript'])
  results.append({"case_id":case_id,"elevenlabs_evidence":SOURCES['elevenlabs'],"sarvam_evidence":SOURCES['sarvam'] if sarvam else None,"shunya_evidence":SOURCES['shunya'],"base_transcript":base['transcript'],"sarvam_transcript":sarvam and sarvam['transcript'],"shunya_transcript":shunya['transcript'],**result})
 output={"policy":policy_sha256(),"scope":"reference-blind local historical transcripts only","results":results}
 target=OUT/'hybrid-v3-outputs.json'; body=json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n'; target.write_text(body,encoding='utf-8')
 lock=hashlib.sha256(target.read_bytes()).hexdigest(); (OUT/'hybrid-v3-output-lock.json').write_text(json.dumps({"HYBRID_V3_OUTPUT_LOCK_SHA256":lock,"cases":30},indent=2)+'\n',encoding='utf-8')
 print(json.dumps({"policy":policy_sha256(),"output_lock":lock,"cases":len(results),"sarvam_missing":sum(not r['sarvam_available'] for r in results),"operations":sum(sum(r['counts'].values()) for r in results)}))
if __name__=='__main__':main()

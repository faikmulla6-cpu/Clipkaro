#!/usr/bin/env python3
"""Sanitize existing clean Hinglish evidence into fusion-only, reference-blind inputs."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'asr-qualification-evidence'/'hinglish-fusion-v1'/'case-alignment.json'
SOURCES={
 "shunya":ROOT/'asr-qualification-evidence'/'shunya-v2-clean'/'shunya-v2-clean.json',
 "elevenlabs":ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'/'elevenlabs-v2-clean.json',
 "sarvam":ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'/'sarvam-v2-clean.json',
 "groq":ROOT/'asr-qualification-evidence'/'api-step2b-2026-08-13'/'groq-results.json',
 "cloudflare":ROOT/'asr-qualification-evidence'/'api-step2b-2026-08-13'/'cloudflare-results.json',
 "deepgram":ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'/'deepgram-v2-clean.json',
 "speechmatics":ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'/'speechmatics-v2-clean.json',
 "assemblyai":ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'/'assemblyai-v2-clean.json',
 "gladia":ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'/'gladia-v2-clean.json',
}

def rows(path:Path):
    return json.loads(path.read_text(encoding='utf-8')).get('results',[])

def main() -> int:
    selected={}
    for provider,path in SOURCES.items():
        chosen={}
        for index,row in enumerate(rows(path)):
            if row.get('language')!='hinglish' or not row.get('success') or not str(row.get('transcript') or '').strip(): continue
            if row.get('scenario') not in (None,'clean'): continue
            case_id=str(row.get('case_id') or ''); sha=str(row.get('audio_sha256') or '')
            if case_id and sha and case_id not in chosen:
                chosen[case_id]={"audio_sha256":sha,"transcript":str(row['transcript']).strip(),"evidence_pointer":f"{path.relative_to(ROOT).as_posix()}#results[{index}]"}
        selected[provider]=chosen
    case_ids=sorted(set().union(*(set(items) for items in selected.values())))
    output=[]
    for case_id in case_ids:
        variants=[(provider,items[case_id]) for provider,items in selected.items() if case_id in items]
        hashes={item['audio_sha256'] for _,item in variants}
        if len(hashes)!=1: raise RuntimeError(f"Audio identity conflict for {case_id}")
        output.append({"case_id":case_id,"audio_sha256":hashes.pop(),"hypotheses":[{"provider":provider,**item} for provider,item in variants],"missing_providers":[provider for provider,items in selected.items() if case_id not in items]})
    if len(output)!=30: raise RuntimeError(f"Expected 30 Hinglish cases, found {len(output)}")
    payload={"schema":"hinglish-fusion-v1-alignment","historical_evidence_only":True,"cases":output}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')
    print(f"cases={len(output)} sha256={hashlib.sha256(OUT.read_bytes()).hexdigest()}")
    return 0
if __name__=='__main__': raise SystemExit(main())

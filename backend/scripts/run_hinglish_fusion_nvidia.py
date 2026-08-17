#!/usr/bin/env python3
"""Reference-blind NVIDIA hosted generation for HinglishFusionV1; never scores outputs."""
from __future__ import annotations
import argparse,asyncio,hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.core.config import get_settings
from app.services.hinglish_fusion import FUSION_MODEL,FUSION_PROMPT_SHA256,anonymized_fusion_messages,assert_reference_blind

URL="https://integrate.api.nvidia.com/v1/chat/completions"
OUT_DIR=ROOT/'asr-qualification-evidence'/'hinglish-fusion-v1'
ALIGNMENT=OUT_DIR/'case-alignment.json'

def write(path:Path,value:dict): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

async def invoke(client:httpx.AsyncClient,key:str,messages:list[dict[str,str]]) -> tuple[str,dict,float]:
    request={"model":FUSION_MODEL,"messages":messages,"temperature":0,"max_tokens":2048,"stream":False,"chat_template_kwargs":{"enable_thinking":False}}
    started=time.perf_counter(); response=await client.post(URL,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=request);latency=time.perf_counter()-started
    if not response.is_success: raise RuntimeError(f"NVIDIA_HTTP_{response.status_code}")
    raw=response.json(); content=str(((raw.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
    if not content: raise RuntimeError('NVIDIA_EMPTY_OUTPUT')
    if '\nHypothesis ' in content or content.lower().startswith(('final:','transcript:')): raise RuntimeError('NVIDIA_NON_TRANSCRIPT_OUTPUT')
    return content,raw.get('usage') or {},latency

async def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');args=parser.parse_args()
    key=get_settings().nvidia_api_key
    if not key: print('CREDENTIAL_REQUIRED: NVIDIA_API_KEY');return 2
    alignment=json.loads(ALIGNMENT.read_text(encoding='utf-8'))['cases']
    cases=[alignment[0],alignment[len(alignment)//2],alignment[-1]] if args.smoke else alignment
    target=OUT_DIR/('nvidia-smoke.json' if args.smoke else 'nvidia-fusion-outputs.json')
    payload=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {"schema":"hinglish-fusion-v1-generation","model":FUSION_MODEL,"endpoint":URL,"temperature":0,"prompt_sha256":FUSION_PROMPT_SHA256,"reference_blind":True,"results":[]}
    # Qualification output is authoritative after its first bounded attempt.
    # Do not regenerate failures after generation; scoring must see them too.
    done={r['case_id'] for r in payload['results']}
    async with httpx.AsyncClient(timeout=90) as client:
        for case in cases:
            if case['case_id'] in done: continue
            sanitized=[{"provider":h['provider'],"transcript":h['transcript']} for h in case['hypotheses']]
            messages,mapping=anonymized_fusion_messages(case['case_id'],sanitized);assert_reference_blind(messages)
            row={"case_id":case['case_id'],"audio_sha256":case['audio_sha256'],"hypothesis_count":len(sanitized),"model":FUSION_MODEL,"temperature":0,"prompt_sha256":FUSION_PROMPT_SHA256,"generated_at":datetime.now(timezone.utc).isoformat()}
            try:
                output,usage,latency=await invoke(client,key,messages)
                row.update({"success":True,"fusion_transcript":output,"latency_seconds":round(latency,4),"usage":{"prompt_tokens":usage.get('prompt_tokens'),"completion_tokens":usage.get('completion_tokens'),"total_tokens":usage.get('total_tokens')}})
                # The anonymous payload is safe for generation evidence. Provider mapping is audit-only and separate.
                row['anonymized_hypotheses']=[{"label":chr(65+i),"transcript":item['transcript']} for i,item in enumerate([sanitized[list(mapping.values()).index(provider)] for provider in mapping.values()])]
                mapping_path=OUT_DIR/'provider-mappings.json'
                mappings=json.loads(mapping_path.read_text(encoding='utf-8')) if mapping_path.exists() else {"schema":"audit-only-provider-mappings","mappings":{}}
                mappings['mappings'][case['case_id']]=mapping;write(mapping_path,mappings)
            except Exception as exc: row.update({"success":False,"error_category":type(exc).__name__,"error":str(exc)[:80]})
            payload['results'].append(row);write(target,payload);print(case['case_id'],row['success'],flush=True)
    if not args.smoke and len(payload['results'])==len(alignment):
        lock=hashlib.sha256(target.read_bytes()).hexdigest();write(OUT_DIR/'fusion-output-lock.json',{"FUSION_OUTPUT_LOCK_SHA256":lock,"output_file":target.name,"case_count":len(alignment)})
        print('FUSION_OUTPUT_LOCK_SHA256='+lock)
    return 0
if __name__=='__main__': raise SystemExit(asyncio.run(main()))

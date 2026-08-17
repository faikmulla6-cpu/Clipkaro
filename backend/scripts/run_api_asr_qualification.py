#!/usr/bin/env python3
"""Resumable real-provider qualification through ClipKaro's API ASR internals.

It deliberately uses the production audio extraction, chunking, provider
normalisation and timestamp code.  Results are persisted after every media item
so a stopped qualification never repays for an already verified request.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from app.core.config import get_settings  # noqa: E402
from app.services.asr_benchmark import error_rate, expected_language_matches, probe_duration, transcript_text, validate_timestamps  # noqa: E402
from app.services.asr_providers import merge_chunk_results, transcribe_api  # noqa: E402
from app.services.asr_quality import assess_transcript  # noqa: E402
from app.services.timestamp_stabilization import stabilize_word_timestamps  # noqa: E402
from app.services.video import chunk_api_audio, extract_api_audio, probe_audio_duration  # noqa: E402

CORPUS_LOCK = "35a7c63d6c2f645fb5b73ef33c2ef1989e9462aba8048b11394d4ae83626a78b"
THRESHOLD_LOCK = "4f5e49ab72cebcf51c58b4f83204b1d9a29e0c607c6b19b5c324806b61f9347e"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def write(path: Path, value: Any) -> None:
    temporary=path.with_suffix('.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    temporary.replace(path)

def refs(entry: dict[str, Any]) -> tuple[float,float,dict[str,dict[str,float]]]:
    hypothesis=entry['transcript']
    source=entry['case']
    raw=source.get('raw_references') or {'reference': source['reference']}
    individual={key:{'wer':round(error_rate(text,hypothesis,unit='word'),4),'cer':round(error_rate(text,hypothesis,unit='char'),4)} for key,text in raw.items()}
    # This minimum-per-metric rule was frozen in the Vaani manifest before any
    # provider calls; preserve individual references as evidence.
    return min(x['wer'] for x in individual.values()), min(x['cer'] for x in individual.values()), individual

async def one(case: dict[str, Any], corpus: Path, provider: str) -> dict[str, Any]:
    path=corpus / (case.get('path') or case.get('audio_path'))
    duration=probe_duration(path); prepared=path.with_name(path.stem+'.qualification.asr.flac'); chunks_dir=prepared.with_suffix('.chunks')
    row={'case_id':case['id'],'provider_target':provider,'audio_sha256':case.get('sha256') or case.get('audio_sha256'),'language':case['language'],'language_hint':case.get('language_hint','auto'),'scenario':case['scenario'],'duration_seconds':round(duration,3),'case':case}
    try:
        await extract_api_audio(path, prepared)
        api_duration=await probe_audio_duration(prepared); settings=get_settings()
        chunks=await chunk_api_audio(prepared,duration=api_duration,output_dir=chunks_dir,chunk_seconds=settings.asr_chunk_seconds,overlap_seconds=settings.asr_chunk_overlap_seconds,max_chunks=settings.asr_api_max_chunks,max_bytes=settings.asr_api_max_chunk_mb*1024*1024)
        results=[]
        for number,(chunk,offset,chunk_duration) in enumerate(chunks):
            result=await transcribe_api(chunk,language_hint=case.get('language_hint','auto'),duration=chunk_duration,request_id=f"qual-{provider}-{case['id']}-{number}")
            results.append((result,offset))
        merged=merge_chunk_results(results)
        # Qualification must validate the exact representation production
        # exposes after its native timestamp cleanup, never raw provider order.
        merged.segments=stabilize_word_timestamps(merged.segments)
        merged.words=[word for segment in merged.segments for word in segment.get('words') or []]
        hypothesis=transcript_text(merged.segments); timestamps=validate_timestamps(merged.segments,duration)
        row.update({'provider':merged.provider,'model':merged.model,'fallback_used':merged.fallback_used,'provider_latency_seconds':round(merged.provider_latency,3),'request_attempts':merged.request_attempts,'retries':max(0,merged.request_attempts-len(results)),'detected_language':merged.language,'language_match':expected_language_matches(case['language'],merged.language),'timestamps_valid':timestamps['valid'],'timestamp_issues':timestamps['issues'],'word_timestamp_count':timestamps['word_count'],'segment_timestamp_count':len(merged.segments),'timestamp_quality':merged.timestamp_quality,'transcript':hypothesis,'transcript_length':len(hypothesis),'rtf':round(merged.provider_latency/max(duration,.001),4)})
        wer,cer,individual=refs(row); row.update({'wer':round(wer,4),'cer':round(cer,4),'individual_reference_scores':individual})
        quality=assess_transcript(merged.segments,case['language']); row.update({'quality_gate_accepted':quality['accepted'],'quality_gate_flags':quality['flags'],'speech_coverage':round(quality['speech_coverage'],4)})
    except Exception as exc:
        # Do not persist provider body/headers or credentials.
        row.update({'error_category':type(exc).__name__,'error':str(exc)[:240],'success':False})
    else: row['success']=True
    finally:
        prepared.unlink(missing_ok=True); shutil.rmtree(chunks_dir,ignore_errors=True)
    row.pop('case',None)
    return row

async def run(args: argparse.Namespace) -> int:
    corpus=ROOT/'stress_corpus'; lock=json.loads((corpus/'corpus-lock.json').read_text(encoding='utf-8'))
    threshold=json.loads((ROOT/'asr-threshold-lock.json').read_text(encoding='utf-8'))['threshold_sha256']
    if lock.get('CORPUS_LOCK_SHA256')!=CORPUS_LOCK or threshold!=THRESHOLD_LOCK: raise RuntimeError('Immutable lock mismatch; refusing provider calls.')
    manifest=json.loads((corpus/'manifest.json').read_text(encoding='utf-8'))
    cases=list(manifest['cases']) + (list(manifest['stress_cases']) if args.scope=='full' else []) + (list(manifest['negative_controls']) if args.scope=='full' else [])
    if args.scope=='clean': cases=list(manifest['cases'])
    if args.scope=='coverage':
        # Fixed representative stress matrix: one deterministic case for every
        # scenario/language pair, plus every clean locked case.  This is the
        # minimum Cloudflare qualification coverage, not a substitute for the
        # complete Groq matrix.
        chosen: dict[tuple[str, str], dict[str, Any]] = {}
        for item in sorted(manifest['stress_cases'], key=lambda row: row['id']):
            chosen.setdefault((item['scenario'], item['language']), item)
        cases=list(manifest['cases']) + [chosen[key] for key in sorted(chosen)]
    evidence=ROOT/'asr-qualification-evidence'/f"api-step2b-{date.today().isoformat()}"; evidence.mkdir(parents=True,exist_ok=True); evidence_path=evidence/f'{args.provider}-results.json'
    payload=json.loads(evidence_path.read_text(encoding='utf-8')) if evidence_path.exists() else {'candidate':'ClipKaro API ASR STEP 2B','provider_target':args.provider,'scope':args.scope,'corpus_lock_before':CORPUS_LOCK,'threshold_lock_before':THRESHOLD_LOCK,'multi_reference_policy':'Per-metric minimum across the three preserved Vaani references, frozen in manifest before provider calls.','results':[]}
    done={(x['case_id'],x.get('audio_sha256')) for x in payload['results']}
    os.environ['ASR_MODE']='api'; os.environ['ASR_PRIMARY_PROVIDER']=args.provider; os.environ['ASR_FALLBACK_PROVIDER']='none'; get_settings.cache_clear()
    for index,case in enumerate(cases,1):
        audio_hash=case.get('sha256') or case.get('audio_sha256')
        if (case['id'],audio_hash) in done: continue
        row=await one(case,corpus,args.provider); payload['results'].append(row); write(evidence_path,payload)
        print(f"{args.provider} {index}/{len(cases)} {case['id']} {'ok' if row['success'] else 'error'}",flush=True)
    payload['corpus_lock_after']=json.loads((corpus/'corpus-lock.json').read_text(encoding='utf-8')).get('CORPUS_LOCK_SHA256'); payload['threshold_lock_after']=json.loads((ROOT/'asr-threshold-lock.json').read_text(encoding='utf-8'))['threshold_sha256']
    write(evidence_path,payload); print(str(evidence_path)); return 0

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--provider',choices=('groq','cloudflare'),required=True); p.add_argument('--scope',choices=('clean','coverage','full'),default='clean'); return asyncio.run(run(p.parse_args()))
if __name__=='__main__': raise SystemExit(main())

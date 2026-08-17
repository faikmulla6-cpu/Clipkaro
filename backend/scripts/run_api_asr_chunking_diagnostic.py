#!/usr/bin/env python3
"""Exercise the real >600-second API chunking path outside the WER corpus."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from app.core.config import get_settings  # noqa: E402
from app.services.asr_benchmark import probe_duration, validate_timestamps  # noqa: E402
from app.services.asr_providers import merge_chunk_results, transcribe_api  # noqa: E402
from app.services.timestamp_stabilization import stabilize_word_timestamps  # noqa: E402
from app.services.video import chunk_api_audio, extract_api_audio, find_media_tool, probe_audio_duration  # noqa: E402


async def main() -> int:
    corpus=ROOT/'stress_corpus'; evidence=ROOT/'asr-qualification-evidence'/'api-step2b-2026-08-13'; evidence.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((corpus/'manifest.json').read_text(encoding='utf-8'))
    selected=[]; total=0.0
    for case in sorted(manifest['cases'],key=lambda row:row['id']):
        selected.append(case); total += float(case['duration'])
        if total > 610: break
    work=evidence/'chunking-diagnostic'; work.mkdir(exist_ok=True); listing=work/'inputs.txt'; joined=work/'long-form.m4a'; prepared=work/'long-form.asr.flac'; chunks_dir=prepared.with_suffix('.chunks')
    # The concat source list is generated locally from locked paths only.
    listing.write_text(''.join("file '"+str((corpus/c['path']).resolve()).replace('\\\\','/')+"'\n" for c in selected),encoding='utf-8')
    ffmpeg=find_media_tool('ffmpeg')
    proc=subprocess.run([ffmpeg,'-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-vn','-c:a','aac','-b:a','96k',str(joined)],capture_output=True,timeout=300,check=False)
    if proc.returncode: raise RuntimeError('Could not build diagnostic long-form fixture.')
    await extract_api_audio(joined,prepared); duration=await probe_audio_duration(prepared); settings=get_settings()
    chunks=await chunk_api_audio(prepared,duration=duration,output_dir=chunks_dir,chunk_seconds=settings.asr_chunk_seconds,overlap_seconds=settings.asr_chunk_overlap_seconds,max_chunks=settings.asr_api_max_chunks,max_bytes=settings.asr_api_max_chunk_mb*1024*1024)
    results=[]
    for i,(chunk,offset,chunk_duration) in enumerate(chunks):
        results.append((await transcribe_api(chunk,language_hint='auto',duration=chunk_duration,request_id=f'step2b-chunk-{i}'),offset))
    merged=merge_chunk_results(results); stabilized=stabilize_word_timestamps(merged.segments); check=validate_timestamps(stabilized,duration)
    words=[word for segment in stabilized for word in segment.get('words') or []]
    duplicates=sum(1 for a,b in zip(stabilized,stabilized[1:]) if str(a['text']).strip().casefold()==str(b['text']).strip().casefold())
    payload={'diagnostic':True,'source_clean_case_ids':[c['id'] for c in selected],'source_duration_seconds':round(total,3),'duration_seconds':round(duration,3),'chunk_threshold_seconds':settings.asr_chunk_seconds,'overlap_seconds':settings.asr_chunk_overlap_seconds,'chunk_count':len(chunks),'chunk_offsets':[round(offset,3) for _,offset,_ in chunks],'provider':merged.provider,'model':merged.model,'segments':len(stabilized),'words':len(words),'timestamp_valid':check['valid'],'timestamp_issues':check['issues'],'chronological':all(float(a['start'])<=float(b['start']) for a,b in zip(stabilized,stabilized[1:])),'duplicate_adjacent_segments':duplicates,'final_timestamp':round(max(s['end'] for s in stabilized),3),'within_duration':max(s['end'] for s in stabilized)<=duration+.75,'passed':len(chunks)>=2 and check['valid'] and duplicates==0 and max(s['end'] for s in stabilized)<=duration+.75}
    (evidence/'chunking-diagnostic.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(payload)); return 0 if payload['passed'] else 1

if __name__=='__main__': raise SystemExit(asyncio.run(main()))

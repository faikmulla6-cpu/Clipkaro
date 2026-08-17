#!/usr/bin/env python3
"""Resumable 90-clean-case V2 candidate screen; never alters production routing."""
from __future__ import annotations
import argparse,asyncio,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.core.config import get_settings
from app.services.asr_benchmark import probe_duration,validate_timestamps,transcript_text
from app.services.asr_policy_v2 import error_rate_v2
from app.services.candidate_asr_providers import ElevenLabsScribeV2Provider,DeepgramNova3Provider,SarvamSaarasV3Provider,SpeechmaticsASRProvider,TrelisTaraASRProvider,AssemblyAIUniversal2Provider,GladiaSolaria1Provider,GeminiASRProvider,ShunyaCodeswitchASRProvider,GnaniPrismaV25Provider,NvidiaParakeetRNNTProvider
from app.services.asr_providers import ASRProviderError
from app.services.timestamp_stabilization import stabilize_word_timestamps
from app.services.video import extract_api_audio
E=ROOT/'asr-qualification-evidence'/'api-step4a-v2-screen'
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
async def main():
 p=argparse.ArgumentParser();p.add_argument('--provider',choices=('elevenlabs','deepgram','sarvam','speechmatics','tara','assemblyai','gladia','gemini','shunya','gnani','nvidia-parakeet'),required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--languages',default='hi,mr,hinglish');p.add_argument('--run-id',default='');p.add_argument('--gemini-api-path',choices=('interactions','generate-content'),default='interactions');args=p.parse_args();s=get_settings()
 languages=tuple(x.strip() for x in args.languages.split(',') if x.strip())
 key={'elevenlabs':s.elevenlabs_api_key,'deepgram':s.deepgram_api_key,'sarvam':s.sarvam_api_key,'speechmatics':s.speechmatics_api_key,'tara':s.trelis_router_api_key,'assemblyai':s.assemblyai_api_key,'gladia':s.gladia_api_key,'gemini':s.gemini_api_key,'shunya':s.shunyalabs_api_key,'gnani':s.gnani_api_key,'nvidia-parakeet':s.nvidia_api_key}[args.provider]
 if not key: print(f'CREDENTIAL_REQUIRED: {args.provider}');return 2
 manifest=json.loads((ROOT/'stress_corpus'/'manifest.json').read_text(encoding='utf-8'))
 evidence_root=ROOT/'asr-qualification-evidence'/f'{args.provider}-v2-clean' if args.provider in {'gemini','shunya'} else E
 run_suffix=f'-{args.run_id}' if args.run_id else ''
 target=evidence_root/f'{args.provider}-v2-{"smoke" if args.smoke else "clean"}{run_suffix}.json'
 payload=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'policy':'asr-policy-v2.json','provider':args.provider,'scope':'diagnostic smoke cases' if args.smoke else f'{len(languages)*30} clean locked cases','languages':languages,'results':[]}
 done={r['case_id'] for r in payload['results']}
 provider=ElevenLabsScribeV2Provider(key,s.asr_provider_timeout_seconds) if args.provider=='elevenlabs' else DeepgramNova3Provider(key,s.asr_provider_timeout_seconds) if args.provider=='deepgram' else SarvamSaarasV3Provider(key,s.asr_provider_timeout_seconds) if args.provider=='sarvam' else SpeechmaticsASRProvider(key,s.asr_provider_timeout_seconds) if args.provider=='speechmatics' else TrelisTaraASRProvider(key,s.asr_provider_timeout_seconds) if args.provider=='tara' else AssemblyAIUniversal2Provider(key,s.asr_provider_timeout_seconds) if args.provider=='assemblyai' else GladiaSolaria1Provider(key,s.asr_provider_timeout_seconds) if args.provider=='gladia' else GeminiASRProvider(key,s.asr_provider_timeout_seconds,args.gemini_api_path) if args.provider=='gemini' else ShunyaCodeswitchASRProvider(key,s.asr_provider_timeout_seconds) if args.provider=='shunya' else GnaniPrismaV25Provider(key,s.asr_provider_timeout_seconds) if args.provider=='gnani' else NvidiaParakeetRNNTProvider(key,s.asr_provider_timeout_seconds)
 cases=[c for c in manifest['cases'] if c['language'] in languages]
 if args.smoke:
  cases=[next(c for c in cases if c['language']==language) for language in languages]
 for case in cases:
  if case['id'] in done:continue
  source=ROOT/'stress_corpus'/case['path']; prepared=source.with_suffix('.candidate.wav' if args.provider=='nvidia-parakeet' else '.candidate.flac')
  row={'case_id':case['id'],'language':case['language'],'audio_sha256':case['sha256'],'api_path':getattr(provider,'api_path',None)}
  try:
   if args.provider=='nvidia-parakeet':
    from app.services.video import extract_audio
    await extract_audio(source,prepared)
   else: await extract_api_audio(source,prepared)
   result=await provider.transcribe(prepared,language_hint=case['language_hint'],duration=probe_duration(source),request_id=f'v2-{args.provider}-{case["id"]}')
   stabilized=stabilize_word_timestamps(result.segments)
   # Sarvam REST exposes phrase timestamps only.  Do not turn them into words.
   segments=stabilized or result.segments
   hypothesis=transcript_text(segments) or result.text
   references=(case.get('raw_references') or {'reference':case['reference']}).values();scores=[(error_rate_v2(ref,hypothesis,unit='word'),error_rate_v2(ref,hypothesis,unit='char')) for ref in references];check=validate_timestamps(segments,probe_duration(source)) if segments else {'valid':False}
   word_timestamp_count=sum(len(segment.get('words') or []) for segment in segments)
   row.update({'success':True,'provider':result.provider,'model':result.model,'transcript':hypothesis,'wer':round(min(x[0] for x in scores),4),'cer':round(min(x[1] for x in scores),4),'timestamps_valid':check['valid'],'word_timestamp_count':word_timestamp_count,'segment_timestamp_count':len(segments),'timestamp_quality':result.timestamp_quality,'provider_latency_seconds':result.provider_latency,'rtf':round(result.provider_latency/max(probe_duration(source),.001),4)})
  except Exception as exc:
   row.update({'success':False,'error_category':type(exc).__name__,'error':str(exc)[:160]})
   if isinstance(exc,ASRProviderError): row.update({'http_status':exc.status_code,'retryable':exc.retryable,'rate_limited':exc.rate_limited})
  finally: prepared.unlink(missing_ok=True)
  payload['results'].append(row);write(target,payload);print(case['id'],row['success'],flush=True)
 if not args.smoke and len(payload['results'])==len(cases):
  summary={}
  for lang in languages:
   rows=[x for x in payload['results'] if x['language']==lang and x.get('success')];summary[lang]={'mean_wer':round(sum(x['wer'] for x in rows)/len(rows),4),'mean_cer':round(sum(x['cer'] for x in rows)/len(rows),4),'timestamp_valid_rate':round(sum(x['timestamps_valid'] for x in rows)/len(rows),4),'word_timestamp_coverage':round(sum(x.get('word_timestamp_count',0)>0 for x in rows)/len(rows),4)}
  payload['summary']=summary;write(target,payload)
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))

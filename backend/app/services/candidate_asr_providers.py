"""Experimental API ASR adapters. Not selected by production ASR routing."""
from __future__ import annotations
import time
import json
import asyncio
import wave
from pathlib import Path
from typing import Any
import httpx
from app.services.asr_providers import ASRProviderError, ASRResult, _float, _normalise, _raise_for_status

ELEVEN_URL="https://api.elevenlabs.io/v1/speech-to-text"
DEEPGRAM_URL="https://api.deepgram.com/v1/listen"
SARVAM_URL="https://api.sarvam.ai/speech-to-text"
SPEECHMATICS_JOBS_URL="https://asr.api.speechmatics.com/v2/jobs"
TRELIS_TRANSCRIBE_URL="https://router.trelis.com/api/v1/transcribe"
ASSEMBLYAI_BASE_URL="https://api.assemblyai.com/v2"
GLADIA_BASE_URL="https://api.gladia.io/v2"
GEMINI_API_BASE_URL="https://generativelanguage.googleapis.com"
GEMINI_MODEL="gemini-3.6-flash"
SHUNYA_TRANSCRIPTIONS_URL="https://asr.shunyalabs.ai/v1/audio/transcriptions"
GNANI_TRANSCRIBE_URL="https://api.vachana.ai/stt/v3"
NVIDIA_RIVA_HOST="grpc.nvcf.nvidia.com:443"
# Verified against the hosted NVIDIA Build model page on 2026-08-14.  This is
# an endpoint routing identifier, not a credential.  Candidate-only adapter.
NVIDIA_PARAKEET_FUNCTION_ID="71203149-d3b7-4460-8231-1be2543a1fca"
NVIDIA_PARAKEET_MODEL="nvidia/parakeet-1.1b-rnnt-multilingual-asr"

GEMINI_TRANSCRIPTION_PROMPT = """Transcribe this audio verbatim. Do not summarize, translate, rewrite grammar, correct speaker mistakes, add explanations, add Markdown, or invent unheard words. Preserve spoken language and script. Hindi and Marathi speech must remain in Devanagari. In Hindi-English code-switched speech, preserve Hindi in Devanagari and spoken English words in Latin script. Return only the required JSON object."""
GEMINI_HINGLISH_CONTROL_PROMPT = """Transcribe this audio verbatim.

Do not translate, summarize, rewrite, correct grammar, or explain anything.

Return only the spoken transcript.

This is Hinglish / Hindi-English code-switched speech.

Preserve Hindi words in Devanagari.

Preserve spoken English words in Latin English script.

Example:
आज meeting cancel हो गई

Do NOT convert English words like \"meeting\" or \"cancel\" into Devanagari.

Do not invent unheard words."""

class ElevenLabsScribeV2Provider:
    name="elevenlabs"; model="scribe_v2"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        data={"model_id":self.model,"timestamps_granularity":"word","tag_audio_events":"false","file_format":"other"}
        if language_hint not in {"","auto","hinglish"}: data["language_code"]=language_hint
        headers={"xi-api-key":self.key};
        if request_id: headers["X-Request-ID"]=request_id
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client: response=await client.post(ELEVEN_URL,headers=headers,data=data,files={"file":(audio.name,f,"audio/flac")})
            _raise_for_status(response,"ElevenLabs")
            raw=response.json(); words=[{"start":_float(w.get("start")),"end":_float(w.get("end")),"word":str(w.get("text") or "").strip()} for w in raw.get("words") or [] if w.get("type","word")=="word"]
            # Scribe's response is word-native; one enclosing segment is safe.
            payload={"language":raw.get("language_code"),"language_probability":raw.get("language_probability"),"text":raw.get("text"),"segments":[{"start":words[0]["start"],"end":words[-1]["end"],"text":raw.get("text"),"words":words}] if words else []}
            return _normalise(payload,self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("ElevenLabs request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("ElevenLabs returned malformed JSON") from exc

class DeepgramNova3Provider:
    name="deepgram"; model="nova-3"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        language={"hinglish":"multi","auto":"multi","":"multi"}.get(language_hint,language_hint)
        params={"model":self.model,"language":language,"punctuate":"true","smart_format":"false","numerals":"false","utterances":"true"}
        headers={"Authorization":f"Token {self.key}","Content-Type":"audio/flac"}
        if request_id: headers["X-Request-ID"]=request_id
        started=time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client: response=await client.post(DEEPGRAM_URL,headers=headers,params=params,content=audio.read_bytes())
            _raise_for_status(response,"Deepgram"); raw=response.json(); channel=raw.get("results",{}).get("channels",[{}])[0]; alt=channel.get("alternatives",[{}])[0]
            words=alt.get("words") or []; utterances=raw.get("results",{}).get("utterances") or []
            segments=[{"start":u.get("start"),"end":u.get("end"),"text":u.get("transcript"),"words":[w for w in words if float(u.get("start",0))<=float(w.get("start",0))<float(u.get("end",0))]} for u in utterances]
            payload={"language":channel.get("detected_language") or language,"text":alt.get("transcript"),"segments":segments or [{"start":words[0].get("start"),"end":words[-1].get("end"),"text":alt.get("transcript"),"words":words}] if words else []}
            return _normalise(payload,self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Deepgram request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Deepgram returned malformed JSON") from exc

class SarvamSaarasV3Provider:
    """Experimental REST adapter; Sarvam REST publishes segment, not word, time."""
    name="sarvam"; model="saaras:v3"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        language,mode={"hi":("hi-IN","verbatim"),"mr":("mr-IN","verbatim"),"hinglish":("hi-IN","codemix"),"auto":("hi-IN","codemix")}.get(language_hint,("hi-IN","verbatim"))
        data={"model":self.model,"language_code":language,"mode":mode,"with_timestamps":"true"}
        headers={"api-subscription-key":self.key}
        if request_id: headers["X-Request-ID"]=request_id
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client: response=await client.post(SARVAM_URL,headers=headers,data=data,files={"file":(audio.name,f,"audio/flac")})
            _raise_for_status(response,"Sarvam"); raw=response.json(); timing=raw.get("timestamps") or {}
            # Official REST timestamps cover phrases/sentences, not words.
            texts=timing.get("words") or []; starts=timing.get("start_time_seconds") or []; ends=timing.get("end_time_seconds") or []
            segments=[{"start":_float(start),"end":_float(end),"text":str(text).strip(),"words":[]} for text,start,end in zip(texts,starts,ends) if str(text).strip() and _float(end)>_float(start)]
            if not segments and str(raw.get("transcript") or "").strip():
                # Do not invent timing: unavailable timestamp evidence remains absent.
                segments=[]
            payload={"language":str(raw.get("language_code") or language).split("-")[0],"language_probability":raw.get("language_probability"),"text":raw.get("transcript"),"segments":segments}
            return _normalise(payload,self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Sarvam request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Sarvam returned malformed JSON") from exc

class SpeechmaticsASRProvider:
    """Experimental Speechmatics Batch SaaS Enhanced adapter; never production-routed."""
    name="speechmatics"; model="enhanced"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        language={"hi":"hi","mr":"mr","hinglish":"hi","auto":"hi","":"hi"}.get(language_hint,"hi")
        config={"type":"transcription","transcription_config":{"language":language,"operating_point":"enhanced"}}
        headers={"Authorization":f"Bearer {self.key}"}
        if request_id: headers["X-Request-ID"]=request_id
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    submit=await client.post(SPEECHMATICS_JOBS_URL,headers=headers,data={"config":json.dumps(config)},files={"data_file":(audio.name,f,"audio/flac")})
                    _raise_for_status(submit,"Speechmatics")
                    job_id=(submit.json().get("id") or submit.json().get("job",{}).get("id"))
                    if not job_id: raise ASRProviderError("Speechmatics returned no job id")
                    deadline=time.monotonic()+max(self.timeout,90)
                    status={}
                    while time.monotonic()<deadline:
                        poll=await client.get(f"{SPEECHMATICS_JOBS_URL}/{job_id}",headers=headers)
                        _raise_for_status(poll,"Speechmatics"); status=poll.json(); state=str(status.get("job",status).get("status") or "").lower()
                        if state=="done": break
                        if state in {"rejected","failed","expired"}: raise ASRProviderError("Speechmatics rejected the transcription request")
                        await asyncio.sleep(.5)
                    else: raise ASRProviderError("Speechmatics batch job timed out",retryable=True)
                    transcript=await client.get(f"{SPEECHMATICS_JOBS_URL}/{job_id}/transcript",headers=headers,params={"format":"json-v2"})
                    _raise_for_status(transcript,"Speechmatics"); raw=transcript.json()
            words=[]
            for item in raw.get("results") or []:
                if item.get("type")!="word": continue
                alternative=(item.get("alternatives") or [{}])[0]
                content=str(alternative.get("content") or "").strip()
                if content: words.append({"start":_float(item.get("start_time")),"end":_float(item.get("end_time")),"word":content,"confidence":alternative.get("confidence")})
            text=" ".join(word["word"] for word in words)
            payload={"language":language,"text":text,"segments":[{"start":words[0]["start"],"end":words[-1]["end"],"text":text,"words":words}] if words else []}
            return _normalise(payload,self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Speechmatics request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Speechmatics returned malformed JSON") from exc

class TrelisTaraASRProvider:
    """Experimental Tara text adapter. Tara provides no word/segment timing."""
    name="trelis_tara"; model="trelis/tara"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        headers={"Authorization":f"Bearer {self.key}"}
        if request_id: headers["X-Request-ID"]=request_id
        # mixed_code is explicitly set for Hinglish; Tara documents this as the native-script-safe mode.
        data={"model":self.model,"language":"hi","mixed_code":"true" if language_hint in {"hinglish","auto"} else "false"}
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client: response=await client.post(TRELIS_TRANSCRIBE_URL,headers=headers,data=data,files={"file":(audio.name,f,"audio/flac")})
            _raise_for_status(response,"Trelis Tara"); raw=response.json(); text=str(raw.get("text") or raw.get("transcript") or "").strip()
            if not text: raise ASRProviderError("Trelis Tara returned no transcript")
            return _normalise({"language":raw.get("language") or "hi","text":text,"segments":[]},self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Trelis Tara request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Trelis Tara returned malformed JSON") from exc

class AssemblyAIUniversal2Provider:
    """Experimental AssemblyAI Universal-2 pre-recorded adapter; never production-routed."""
    name="assemblyai"; model="universal-2"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        headers={"Authorization":self.key}
        if request_id: headers["X-Request-ID"]=request_id
        config={"speech_models":[self.model],"format_text":False,"filter_profanity":False}
        if language_hint=="hinglish": config["language_codes"]=["en","hi"]
        else: config["language_code"]={"hi":"hi","mr":"mr"}.get(language_hint,"hi")
        started=time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                upload=await client.post(f"{ASSEMBLYAI_BASE_URL}/upload",headers={**headers,"Content-Type":"application/octet-stream"},content=audio.read_bytes())
                _raise_for_status(upload,"AssemblyAI"); upload_url=upload.json().get("upload_url")
                if not upload_url: raise ASRProviderError("AssemblyAI returned no upload URL")
                submit=await client.post(f"{ASSEMBLYAI_BASE_URL}/transcript",headers=headers,json={"audio_url":upload_url,**config})
                _raise_for_status(submit,"AssemblyAI"); transcript_id=submit.json().get("id")
                if not transcript_id: raise ASRProviderError("AssemblyAI returned no transcript id")
                deadline=time.monotonic()+max(self.timeout,120); raw={}
                while time.monotonic()<deadline:
                    poll=await client.get(f"{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}",headers=headers)
                    _raise_for_status(poll,"AssemblyAI"); raw=poll.json(); state=str(raw.get("status") or "").lower()
                    if state=="completed": break
                    if state=="error": raise ASRProviderError("AssemblyAI rejected the transcription request")
                    await asyncio.sleep(.5)
                else: raise ASRProviderError("AssemblyAI transcription timed out",retryable=True)
            words=[{"start":_float(w.get("start"))/1000,"end":_float(w.get("end"))/1000,"word":str(w.get("text") or "").strip(),"confidence":w.get("confidence")} for w in raw.get("words") or [] if str(w.get("text") or "").strip()]
            text=str(raw.get("text") or "").strip()
            payload={"language":raw.get("language_code") or ("hi" if language_hint=="hinglish" else config.get("language_code")),"text":text,"segments":[{"start":words[0]["start"],"end":words[-1]["end"],"text":text,"words":words}] if words else []}
            return _normalise(payload,self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("AssemblyAI request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("AssemblyAI returned malformed JSON") from exc

class GladiaSolaria1Provider:
    """Experimental Gladia Solaria-1 pre-recorded adapter; never production-routed."""
    name="gladia"; model="solaria-1"
    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        headers={"x-gladia-key":self.key}
        if request_id: headers["X-Request-ID"]=request_id
        languages={"hi":["hi"],"mr":["mr"],"hinglish":["hi","en"]}.get(language_hint,["hi"])
        config={"model":self.model,"language_config":{"languages":languages,"code_switching":language_hint=="hinglish"},"translation":False,"diarization":False,"sentences":True,"punctuation_enhanced":False}
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    upload=await client.post(f"{GLADIA_BASE_URL}/upload",headers=headers,files={"audio":(audio.name,f,"audio/flac")})
                    _raise_for_status(upload,"Gladia"); audio_url=upload.json().get("audio_url")
                    if not audio_url: raise ASRProviderError("Gladia returned no upload URL")
                    submit=await client.post(f"{GLADIA_BASE_URL}/pre-recorded",headers={**headers,"Content-Type":"application/json"},json={"audio_url":audio_url,**config})
                    _raise_for_status(submit,"Gladia"); job=submit.json(); result_url=job.get("result_url") or (f"{GLADIA_BASE_URL}/pre-recorded/{job.get('id')}" if job.get("id") else "")
                    if not result_url: raise ASRProviderError("Gladia returned no result URL")
                    deadline=time.monotonic()+max(self.timeout,120); raw={}
                    while time.monotonic()<deadline:
                        poll=await client.get(result_url,headers=headers); _raise_for_status(poll,"Gladia"); raw=poll.json(); state=str(raw.get("status") or "").lower()
                        if state=="done": break
                        if state in {"error","failed"}: raise ASRProviderError("Gladia rejected the transcription request")
                        await asyncio.sleep(.5)
                    else: raise ASRProviderError("Gladia transcription timed out",retryable=True)
            transcription=(raw.get("result") or {}).get("transcription") or raw.get("transcription") or {}
            utterances=transcription.get("utterances") or []
            segments=[]
            for utterance in utterances:
                words=[{"start":_float(w.get("start")),"end":_float(w.get("end")),"word":str(w.get("word") or "").strip(),"confidence":w.get("confidence")} for w in utterance.get("words") or [] if str(w.get("word") or "").strip()]
                if words: segments.append({"start":_float(utterance.get("start") or words[0]["start"]),"end":_float(utterance.get("end") or words[-1]["end"]),"text":str(utterance.get("text") or " ".join(w["word"] for w in words)),"words":words})
            text=str(transcription.get("full_transcript") or transcription.get("text") or " ".join(s["text"] for s in segments)).strip()
            if not text: raise ASRProviderError("Gladia returned no transcript")
            return _normalise({"language":languages[0],"text":text,"segments":segments},self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Gladia request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Gladia returned malformed JSON") from exc

class GeminiASRProvider:
    """Experimental Gemini Files API text-quality adapter; never production-routed.

    Gemini does not document provider-native ASR word timestamps for this flow,
    so this adapter intentionally emits no words or synthetic timing.
    """
    name="gemini"; model=GEMINI_MODEL
    def __init__(self,key:str,timeout:float=90,api_path:str="interactions"):
        if api_path not in {"interactions","generate-content"}: raise ValueError("Gemini api_path must be interactions or generate-content")
        self.key,self.timeout,self.api_path=key,timeout,api_path

    @staticmethod
    def _response_text(raw:dict[str,Any]) -> str:
        for key in ("output_text","outputText","text"):
            value=raw.get(key)
            if isinstance(value,str) and value.strip(): return value
        found=[]
        def visit(value:Any) -> None:
            if isinstance(value,dict):
                if isinstance(value.get("text"),str): found.append(value["text"])
                for child in value.values(): visit(child)
            elif isinstance(value,list):
                for child in value: visit(child)
        visit(raw.get("output") or raw.get("steps") or raw.get("candidates") or [])
        return "\n".join(found).strip()

    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        headers={"x-goog-api-key":self.key}
        if request_id: headers["X-Request-ID"]=request_id
        file_name=""
        started=time.perf_counter()
        schema={"type":"object","properties":{"transcript":{"type":"string"},"detected_languages":{"type":"array","items":{"type":"string"}}},"required":["transcript","detected_languages"]}
        try:
            async with httpx.AsyncClient(timeout=self.timeout,follow_redirects=False) as client:
                size=audio.stat().st_size
                start_headers={**headers,"X-Goog-Upload-Protocol":"resumable","X-Goog-Upload-Command":"start","X-Goog-Upload-Header-Content-Length":str(size),"X-Goog-Upload-Header-Content-Type":"audio/flac","Content-Type":"application/json"}
                upload_start=await client.post(f"{GEMINI_API_BASE_URL}/upload/v1beta/files",headers=start_headers,json={"file":{"display_name":audio.name}})
                _raise_for_status(upload_start,"Gemini Files API")
                upload_url=upload_start.headers.get("X-Goog-Upload-URL")
                if not upload_url: raise ASRProviderError("Gemini Files API returned no resumable upload URL")
                upload=await client.post(upload_url,headers={"X-Goog-Upload-Command":"upload, finalize","X-Goog-Upload-Offset":"0","Content-Length":str(size)},content=audio.read_bytes())
                _raise_for_status(upload,"Gemini Files API")
                file_info=upload.json().get("file") or upload.json(); file_name=str(file_info.get("name") or "")
                file_uri=str(file_info.get("uri") or "")
                if not file_name or not file_uri: raise ASRProviderError("Gemini Files API returned incomplete file metadata")
                deadline=time.monotonic()+max(self.timeout,120)
                while str(file_info.get("state") or "ACTIVE").upper()=="PROCESSING" and time.monotonic()<deadline:
                    await asyncio.sleep(.5)
                    poll=await client.get(f"{GEMINI_API_BASE_URL}/v1beta/{file_name}",headers=headers)
                    _raise_for_status(poll,"Gemini Files API"); file_info=poll.json(); file_uri=str(file_info.get("uri") or file_uri)
                if str(file_info.get("state") or "ACTIVE").upper()!="ACTIVE": raise ASRProviderError("Gemini uploaded file did not become active",retryable=True)
                mime_type=str(file_info.get("mime_type") or file_info.get("mimeType") or "audio/flac")
                if self.api_path=="interactions":
                    request={"model":self.model,"input":[{"type":"text","text":GEMINI_TRANSCRIPTION_PROMPT},{"type":"audio","uri":file_uri,"mime_type":mime_type}],"response_format":{"type":"text","mime_type":"application/json","schema":schema}}
                    response=await client.post(f"{GEMINI_API_BASE_URL}/v1beta/interactions",headers={**headers,"Content-Type":"application/json"},json=request)
                else:
                    request={"contents":[{"role":"user","parts":[{"text":GEMINI_HINGLISH_CONTROL_PROMPT},{"file_data":{"mime_type":mime_type,"file_uri":file_uri}}]}]}
                    response=await client.post(f"{GEMINI_API_BASE_URL}/v1beta/models/{self.model}:generateContent",headers={**headers,"Content-Type":"application/json"},json=request)
                _raise_for_status(response,"Gemini")
                raw=response.json(); output=self._response_text(raw)
                if self.api_path=="interactions":
                    try: structured=json.loads(output)
                    except (TypeError,json.JSONDecodeError) as exc: raise ASRProviderError("Gemini returned malformed structured transcription") from exc
                    text=str(structured.get("transcript") or "").strip(); languages=structured.get("detected_languages") or []
                else: text=output.strip(); languages=[]
                if not text: raise ASRProviderError("Gemini returned an empty transcript")
                language=str(languages[0]) if languages else ("hi" if language_hint=="hinglish" else language_hint)
                return _normalise({"language":language,"text":text,"segments":[]},self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Gemini request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Gemini returned malformed JSON") from exc
        finally:
            if file_name:
                try:
                    async with httpx.AsyncClient(timeout=15) as cleanup_client:
                        await cleanup_client.delete(f"{GEMINI_API_BASE_URL}/v1beta/{file_name}",headers=headers)
                except (httpx.HTTPError, OSError):
                    pass

class ShunyaCodeswitchASRProvider:
    """Experimental Shunya Zero Codeswitch adapter; never production-routed."""
    name="shunya"; model="zero-codeswitch"
    def __init__(self,key:str,timeout:float=90): self.key,self.timeout=key,timeout
    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        # Shunya documents ISO hints or auto, not a combined hi-en language code.
        data={"model":self.model,"language_code":"auto","response_format":"verbose_json","word_timestamps":"true"}
        headers={"Authorization":f"Bearer {self.key}"}
        if request_id: headers["X-Request-ID"]=request_id
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response=await client.post(SHUNYA_TRANSCRIPTIONS_URL,headers=headers,data=data,files={"file":(audio.name,f,"audio/flac")})
            _raise_for_status(response,"Shunya")
            raw=response.json(); segments=[]
            for segment in raw.get("segments") or []:
                words=[]
                for word in segment.get("words") or []:
                    text=str(word.get("word") or word.get("text") or "").strip()
                    if text:
                        item={"start":_float(word.get("start")),"end":_float(word.get("end")),"word":text}
                        if word.get("confidence") is not None: item["confidence"]=word["confidence"]
                        elif word.get("score") is not None: item["confidence"]=word["score"]
                        words.append(item)
                segments.append({"start":_float(segment.get("start")),"end":_float(segment.get("end")),"text":str(segment.get("text") or "").strip(),"words":words})
            top_words=raw.get("words") or []
            if not segments and top_words:
                words=[{"start":_float(w.get("start")),"end":_float(w.get("end")),"word":str(w.get("word") or w.get("text") or "").strip(),"confidence":w.get("confidence",w.get("score"))} for w in top_words if str(w.get("word") or w.get("text") or "").strip()]
                if words: segments=[{"start":words[0]["start"],"end":words[-1]["end"],"text":str(raw.get("text") or "").strip(),"words":words}]
            text=str(raw.get("text") or raw.get("transcript") or " ".join(s["text"] for s in segments)).strip()
            if not text: raise ASRProviderError("Shunya returned an empty transcript")
            return _normalise({"language":raw.get("detected_language") or "auto","text":text,"segments":segments},self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Shunya request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Shunya returned malformed JSON") from exc


class GnaniPrismaV25Provider:
    """Experimental Gnani Prisma v2.5 adapter; never production-routed.

    Gnani's current REST example documents a direct multipart upload and a
    transcript-only response.  It does not document word/segment timing for
    this endpoint, so this adapter intentionally exposes no synthetic timing.
    The ``hi-IN`` hint is Gnani's documented Hindi mode; code switching is a
    native model capability, not an undocumented request flag.
    """
    name="gnani"; model="prisma-v2.5"

    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout

    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        language={"hi":"hi-IN","mr":"mr-IN","hinglish":"hi-IN","auto":"hi-IN","":"hi-IN"}.get(language_hint,"hi-IN")
        data={
            "language_code":language,
            "preferred_language":language,
            "format":"transcribe",
            # Keep provider-side inverse-text-normalisation disabled so the
            # benchmark scores the provider's spoken-text output faithfully.
            "itn_native_numerals":"false",
        }
        headers={"X-API-Key-ID":self.key}
        if request_id: headers["X-Request-ID"]=request_id
        started=time.perf_counter()
        try:
            with audio.open("rb") as f:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response=await client.post(GNANI_TRANSCRIBE_URL,headers=headers,data=data,files={"audio_file":(audio.name,f,"audio/flac")})
            _raise_for_status(response,"Gnani")
            raw=response.json()
            if raw.get("success") is False:
                raise ASRProviderError("Gnani rejected the transcription request")
            text=str(raw.get("transcript") or raw.get("text") or "").strip()
            if not text: raise ASRProviderError("Gnani returned an empty transcript")
            return _normalise({"language":language.split("-")[0],"text":text,"segments":[]},self.name,self.model,duration,time.perf_counter()-started,1)
        except (httpx.TimeoutException,httpx.NetworkError) as exc: raise ASRProviderError("Gnani request timed out",retryable=True) from exc
        except ValueError as exc: raise ASRProviderError("Gnani returned malformed JSON") from exc


class NvidiaParakeetRNNTProvider:
    """Experimental NVIDIA hosted Riva Parakeet RNNT adapter.

    The Riva client is imported only when this experimental candidate is used;
    it is not a production routing dependency.  The hosted model's documented
    ``multi`` configuration retains automatic spoken-language detection.
    """
    name="nvidia_parakeet"; model=NVIDIA_PARAKEET_MODEL
    function_id=NVIDIA_PARAKEET_FUNCTION_ID

    def __init__(self,key:str,timeout:float=45): self.key,self.timeout=key,timeout

    @staticmethod
    def _seconds(value:Any) -> float:
        """Convert Riva protobuf Duration values without synthesising timing."""
        if hasattr(value,"seconds"):
            return _float(float(value.seconds)+float(getattr(value,"nanos",0))/1_000_000_000)
        return _float(value)

    def _recognize(self,audio:Path):
        try:
            import riva.client as riva_client
        except ImportError as exc:
            raise ASRProviderError("NVIDIA Riva client dependency is not installed") from exc
        try:
            with wave.open(str(audio),"rb") as handle:
                if handle.getnchannels()!=1 or handle.getsampwidth()!=2:
                    raise ASRProviderError("NVIDIA Parakeet requires 16-bit mono WAV audio")
                sample_rate=handle.getframerate(); raw_audio=handle.readframes(handle.getnframes())
            auth=riva_client.Auth(
                uri=NVIDIA_RIVA_HOST,use_ssl=True,
                metadata_args=[["function-id",self.function_id],["authorization",f"Bearer {self.key}"]],
                options=[("grpc.max_receive_message_length",32*1024*1024)],
            )
            config=riva_client.RecognitionConfig(
                encoding=riva_client.AudioEncoding.LINEAR_PCM,
                sample_rate_hertz=sample_rate,
                language_code="multi",
                enable_word_time_offsets=True,
                enable_automatic_punctuation=True,
                max_alternatives=1,
            )
            return riva_client.ASRService(auth).offline_recognize(raw_audio,config)
        except ASRProviderError: raise
        except Exception as exc:
            # gRPC status details can include endpoint internals; retain only a
            # stable category and never surface request metadata or credentials.
            code=getattr(exc,"code",lambda:None)()
            name=getattr(code,"name",str(code or ""))
            if name=="RESOURCE_EXHAUSTED":
                raise ASRProviderError("NVIDIA Parakeet rate limited",retryable=True,rate_limited=True,status_code=429) from exc
            if name in {"UNAVAILABLE","DEADLINE_EXCEEDED","INTERNAL","UNKNOWN"}:
                raise ASRProviderError("NVIDIA Parakeet temporary failure",retryable=True,status_code=503) from exc
            raise ASRProviderError("NVIDIA Parakeet rejected the transcription request") from exc

    async def transcribe(self,audio:Path,*,language_hint:str,duration:float,request_id:str="") -> ASRResult:
        # language_hint is deliberately ignored: this screen measures native
        # multilingual automatic detection rather than a ground-truth-selected language.
        started=time.perf_counter()
        try: response=await asyncio.wait_for(asyncio.to_thread(self._recognize,audio),timeout=self.timeout)
        except asyncio.TimeoutError as exc: raise ASRProviderError("NVIDIA Parakeet request timed out",retryable=True) from exc
        alternatives=[alternative for result in response.results for alternative in result.alternatives]
        if not alternatives: raise ASRProviderError("NVIDIA Parakeet returned no transcription alternatives")
        alternative=alternatives[0]
        words=[]
        for item in alternative.words:
            text=str(item.word or "").strip()
            start,end=self._seconds(item.start_time),self._seconds(item.end_time)
            if text and end>start:
                row={"start":start,"end":end,"word":text}
                if item.confidence: row["confidence"]=_float(item.confidence)
                words.append(row)
        text=str(alternative.transcript or "").strip()
        segments=[{"start":words[0]["start"],"end":words[-1]["end"],"text":text,"words":words}] if words else []
        return _normalise({"language":alternative.language_code or "auto","text":text,"segments":segments},self.name,self.model,duration,time.perf_counter()-started,1)

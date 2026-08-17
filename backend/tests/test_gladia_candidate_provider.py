from pathlib import Path
import httpx
import pytest
from app.services.candidate_asr_providers import GladiaSolaria1Provider

@pytest.mark.asyncio
@pytest.mark.parametrize(("hint","languages","switching"),[("hi",["hi"],False),("mr",["mr"],False),("hinglish",["hi","en"],True)])
async def test_gladia_uses_solaria_and_native_word_timestamps(monkeypatch,tmp_path,hint,languages,switching):
    calls=[]
    async def post(self,url,**kwargs):
        calls.append((url,kwargs))
        if url.endswith('/upload'): return httpx.Response(200,json={'audio_url':'https://api.gladia.io/file/test'},request=httpx.Request('POST',url))
        return httpx.Response(201,json={'id':'job-1','result_url':'https://api.gladia.io/v2/pre-recorded/job-1'},request=httpx.Request('POST',url))
    async def get(self,url,**kwargs):
        return httpx.Response(200,json={'status':'done','result':{'transcription':{'full_transcript':'नमस्ते hello','utterances':[{'start':.1,'end':.9,'text':'नमस्ते hello','words':[{'word':'नमस्ते','start':.1,'end':.4,'confidence':.9},{'word':'hello','start':.5,'end':.9,'confidence':.8}]}]}}},request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post);monkeypatch.setattr(httpx.AsyncClient,'get',get)
    audio=Path(tmp_path)/'sample.flac';audio.write_bytes(b'fixture')
    result=await GladiaSolaria1Provider('test-key').transcribe(audio,language_hint=hint,duration=1)
    config=calls[1][1]['json'];assert config['model']=='solaria-1';assert config['language_config']=={'languages':languages,'code_switching':switching};assert result.segments[0]['words'][0]['start']==.1

from pathlib import Path
import httpx
import pytest
from app.services.candidate_asr_providers import AssemblyAIUniversal2Provider

@pytest.mark.asyncio
@pytest.mark.parametrize(("hint","field","value"),[("hi","language_code","hi"),("mr","language_code","mr"),("hinglish","language_codes",["en","hi"])])
async def test_assemblyai_uses_universal_2_and_real_words(monkeypatch,tmp_path,hint,field,value):
    requests=[]
    async def post(self,url,**kwargs):
        requests.append((url,kwargs))
        if url.endswith('/upload'): return httpx.Response(200,json={'upload_url':'https://private/upload'},request=httpx.Request('POST',url))
        return httpx.Response(200,json={'id':'transcript-1'},request=httpx.Request('POST',url))
    async def get(self,url,**kwargs):
        return httpx.Response(200,json={'status':'completed','text':'नमस्ते hello','language_code':'hi','words':[{'start':100,'end':500,'text':'नमस्ते','confidence':.9},{'start':600,'end':900,'text':'hello','confidence':.8}]},request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post);monkeypatch.setattr(httpx.AsyncClient,'get',get)
    audio=Path(tmp_path)/'sample.flac';audio.write_bytes(b'fixture')
    result=await AssemblyAIUniversal2Provider('test-key').transcribe(audio,language_hint=hint,duration=2)
    config=requests[1][1]['json'];assert config['speech_models']==['universal-2'];assert config['format_text'] is False;assert config[field]==value
    assert result.segments[0]['words'][0]['start']==.1 and result.segments[0]['words'][1]['end']==.9

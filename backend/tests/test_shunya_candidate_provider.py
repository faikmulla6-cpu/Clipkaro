from pathlib import Path
import httpx
import pytest
from app.services.candidate_asr_providers import ShunyaCodeswitchASRProvider

@pytest.mark.asyncio
async def test_shunya_codeswitch_uses_auto_and_native_word_timestamps(monkeypatch,tmp_path):
    calls=[]
    async def post(self,url,**kwargs):
        calls.append((url,kwargs))
        return httpx.Response(200,json={"text":"नमस्ते meeting","detected_language":"Hinglish","segments":[{"start":.1,"end":1.2,"text":"नमस्ते meeting","words":[{"word":"नमस्ते","start":.1,"end":.5,"score":.9},{"word":"meeting","start":.6,"end":1.2,"confidence":.8}]}]},request=httpx.Request("POST",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",post)
    audio=Path(tmp_path)/"sample.flac";audio.write_bytes(b"fixture")
    result=await ShunyaCodeswitchASRProvider("test-key").transcribe(audio,language_hint="hinglish",duration=2)
    assert calls[0][0]=="https://asr.shunyalabs.ai/v1/audio/transcriptions"
    assert calls[0][1]["data"]=={"model":"zero-codeswitch","language_code":"auto","response_format":"verbose_json","word_timestamps":"true"}
    assert result.text=="नमस्ते meeting" and result.segments[0]["words"][0]["confidence"]==.9

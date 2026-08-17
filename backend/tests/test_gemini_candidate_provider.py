import json
from pathlib import Path
import httpx
import pytest
from app.services.candidate_asr_providers import GeminiASRProvider, GEMINI_MODEL

@pytest.mark.asyncio
async def test_gemini_uses_files_structured_output_and_deletes_upload(monkeypatch,tmp_path):
    calls=[]
    async def post(self,url,**kwargs):
        calls.append(("post",url,kwargs))
        req=httpx.Request("POST",url)
        if "upload/v1beta/files" in url: return httpx.Response(200,headers={"X-Goog-Upload-URL":"https://upload.example/session"},request=req)
        if "upload.example" in url: return httpx.Response(200,json={"file":{"name":"files/test","uri":"gemini://files/test","state":"ACTIVE","mime_type":"audio/flac"}},request=req)
        return httpx.Response(200,json={"steps":[{"type":"model_output","content":[{"type":"text","text":json.dumps({"transcript":"नमस्ते hello","detected_languages":["hi","en"]})}]}]},request=req)
    async def delete(self,url,**kwargs): calls.append(("delete",url,kwargs)); return httpx.Response(204,request=httpx.Request("DELETE",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",post);monkeypatch.setattr(httpx.AsyncClient,"delete",delete)
    audio=Path(tmp_path)/"sample.flac";audio.write_bytes(b"fixture")
    result=await GeminiASRProvider("test-key").transcribe(audio,language_hint="hinglish",duration=1,request_id="req-1")
    assert result.provider=="gemini" and result.model==GEMINI_MODEL and result.text=="नमस्ते hello" and result.segments==[]
    assert calls[0][2]["headers"]["X-Goog-Upload-Protocol"]=="resumable"
    request=calls[2][2]["json"];assert request["model"]==GEMINI_MODEL and request["response_format"]=={"type":"text","mime_type":"application/json","schema":{"type":"object","properties":{"transcript":{"type":"string"},"detected_languages":{"type":"array","items":{"type":"string"}}},"required":["transcript","detected_languages"]}}
    assert any(call[0]=="delete" and call[1].endswith("/files/test") for call in calls)

@pytest.mark.asyncio
async def test_gemini_generate_content_control_uses_unstructured_hinglish_prompt(monkeypatch,tmp_path):
    calls=[]
    async def post(self,url,**kwargs):
        calls.append((url,kwargs)); request=httpx.Request("POST",url)
        if "upload/v1beta/files" in url: return httpx.Response(200,headers={"X-Goog-Upload-URL":"https://upload.example/session"},request=request)
        if "upload.example" in url: return httpx.Response(200,json={"file":{"name":"files/test","uri":"gemini://files/test","state":"ACTIVE"}},request=request)
        return httpx.Response(200,json={"candidates":[{"content":{"parts":[{"text":"आज meeting cancel हो गई"}]}}]},request=request)
    async def delete(self,url,**kwargs): return httpx.Response(204,request=httpx.Request("DELETE",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",post);monkeypatch.setattr(httpx.AsyncClient,"delete",delete)
    audio=Path(tmp_path)/"sample.flac";audio.write_bytes(b"fixture")
    result=await GeminiASRProvider("test-key",api_path="generate-content").transcribe(audio,language_hint="hinglish",duration=1)
    assert result.text=="आज meeting cancel हो गई" and "/models/gemini-3.6-flash:generateContent" in calls[2][0]
    assert "Do NOT convert English words" in calls[2][1]["json"]["contents"][0]["parts"][0]["text"]

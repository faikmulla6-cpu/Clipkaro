import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.services.cartoon_story import normalize_director_story, StoryValidationError, RATIOS, director_prompt
from app.services.cartoon_story_render import build_story_project, schedule_speech
from story_v3_fixtures import fixtures


def story():
    return normalize_director_story(fixtures()["jannat"],duration=30)


@pytest.mark.asyncio
async def test_postgres_startup_accepts_the_actual_migration_head(monkeypatch):
    from types import SimpleNamespace
    from contextlib import asynccontextmanager
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.core import database

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    connection = SimpleNamespace(fetchval=AsyncMock(return_value=head))

    @asynccontextmanager
    async def acquire():
        yield connection

    monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(normalized_database_backend="postgres"))
    monkeypatch.setattr(database, "_get_postgres_pool", AsyncMock(return_value=SimpleNamespace(acquire=acquire)))
    await database.init_db()
    connection.fetchval.assert_awaited_once()
    connection.fetchval.return_value = "outdated-revision"
    with pytest.raises(RuntimeError, match="schema is not current"):
        await database.init_db()


def audio_for(story):
    return [{"id":line["id"],"filename":line["id"]+".mp3","duration":2,
             "word_boundaries":[{"text":line["text"].split()[0],"offset":1000000,"duration":5000000}],
             "lip_envelope":[0,.5,.8,0]} for scene in story["scenes"] for line in scene["speech"]]


def test_director_contract_preserves_action_sequences_identities_and_variable_scene_lengths():
    s=story()
    assert [x["duration"] for x in s["scenes"]]==[7,8,5,10]
    assert s["scenes"][-1]["actions"][1]["type"]=="walk"
    assert s["scenes"][-1]["actions"][1]["to"]["x"]==.72
    assert s["characters"][0]["appearance"]["hair_style"]=="long"
    assert s["scenes"][1]["camera"][0]["shot"]=="close"
    assert s["scenes"][0]["speech"][0]["track"]=="narration"


def test_carried_objects_persist_between_locations_but_memory_does_not_leak_into_present():
    raw=fixtures()
    library=normalize_director_story(raw["library"],duration=15)
    book=next(p for p in library["scenes"][1]["props"] if p["id"]=="book")
    assert book["holder_id"]=="mira" and book["support_id"] is None
    assert not any(p["id"]=="pendant" for p in story()["scenes"][-1]["props"])


@pytest.mark.parametrize("corrupt",["identity","action","target","camera","nan","duration","duplicates"])
def test_invalid_director_data_fails_before_render_or_provider_calls(corrupt):
    raw=fixtures()["jannat"]
    if corrupt=="identity":raw["scenes"][0]["character_ids"]=["missing"]
    if corrupt=="action":raw["scenes"][0]["actions"][0]["type"]="eval"
    if corrupt=="target":raw["scenes"][2]["actions"][1]["target_id"]="not-present"
    if corrupt=="camera":raw["scenes"][0]["camera"][0]["focus_id"]="missing"
    if corrupt=="nan":raw["scenes"][0]["duration"]=float("nan")
    if corrupt=="duration":raw["scenes"][0]["actions"][0]["end"]=0
    if corrupt=="duplicates":raw["characters"].append(copy.deepcopy(raw["characters"][0]))
    with pytest.raises(StoryValidationError):normalize_director_story(raw,duration=30)


def test_actual_speech_lengths_move_conflicting_narration_and_dialogue_without_overlap():
    s=story();s["scenes"][0]["speech"].append({"id":"second","track":"dialogue","speaker_id":"jannat","text":"Hello","start":.6})
    assets=audio_for(s)
    _,tracks,words=schedule_speech(s,assets)
    assert tracks[1]["start_seconds"]>=tracks[0]["start_seconds"]+2+.19
    assert all(w["source"]=="tts_word_boundary" for w in words)


def test_measured_speech_recovers_late_cues_without_truncating():
    s = story()
    scene = s["scenes"][0]
    scene["speech"][0]["start"] = 5.5
    scene["speech"].append({"id": "second", "track": "dialogue", "speaker_id": "jannat",
                            "text": "Kaun hai?", "start": 6.5})
    _, tracks, _ = schedule_speech(s, audio_for(s))
    first, second = tracks[:2]
    assert first["start_seconds"] < 5.5
    assert second["start_seconds"] >= first["start_seconds"] + 2.19
    assert second["start_seconds"] + second["duration_seconds"] <= scene["duration"]
    assert [track["duration_seconds"] for track in (first, second)] == [2, 2]


def test_missing_narration_and_oversized_or_untimed_speech_cannot_silently_render():
    s=story();a=audio_for(s)
    with pytest.raises(StoryValidationError,match="no audio"):schedule_speech(s,a[1:])
    a[0]["duration"]=20
    with pytest.raises(StoryValidationError,match="does not fit"):schedule_speech(s,a)
    a=audio_for(s);a[0]["word_boundaries"]=[]
    with pytest.raises(StoryValidationError,match="word timestamps"):schedule_speech(s,a)


@pytest.mark.parametrize("ratio",RATIOS)
@pytest.mark.parametrize("case",["jannat","garden","library"])
def test_all_story_types_and_selectable_ratios_compile_to_native_hyperframes(ratio,case):
    raw=fixtures()[case];duration=30 if case=="jannat" else 10 if case=="garden" else 12
    s=normalize_director_story(raw,duration=duration)
    language={"jannat":"ur","garden":"en","library":"hinglish"}[case]
    files=build_story_project({"duration_seconds":duration,"aspect_ratio":ratio,"language":language},s,audio_for(s))
    w,h,_=RATIOS[ratio]
    assert f'data-width="{w}" data-height="{h}"' in files["index.html"]
    assert '"kind": "story-v3"' in files["index.html"]
    assert ('dir="rtl"' in files["index.html"])==(language=="ur")
    assert "staticFile" not in files["index.html"] and "remotion" not in files["index.html"].lower()
    assert len(json.loads(files["audio-timeline.json"])["tracks"])==len(audio_for(s))


def test_prompt_lists_executable_supported_verbs_instead_of_only_action_sentences():
    prompt=director_prompt(30,"ur","2d-cartoon","A short suspense story")
    assert "schema_version:3" in prompt and "pick_up" in prompt and "camera" in prompt and "speech" in prompt


def test_caption_markup_escapes_untrusted_text_and_preserves_measured_end():
    s=story();a=audio_for(s);a[0]["word_boundaries"][0]["text"]="<script>alert(1)</script>"
    html=build_story_project({"duration_seconds":30,"aspect_ratio":"4:5","language":"hi"},s,a)["index.html"]
    assert "&lt;script&gt;" in html and "<script>alert" not in html
    assert 'data-duration="0.5000"' in html or 'data-duration="0.5"' in html


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["garden", "library", "jannat", "absolute-time", "truncated", "unreadable", "missing-target"])
async def test_mocked_glm_response_enters_director_contract_without_network(monkeypatch, case):
    from app.services import cartoon_job as job
    import httpx

    raw = fixtures().get(case, fixtures()["jannat"])
    if case == "missing-target":
        raw["scenes"][0]["actions"][0]["target_id"] = "missing"
    if case == "absolute-time":
        scene = raw["scenes"][2]
        scene["props"][1]["id"] = "old pendant"
        scene["actions"][1]["target_id"] = "old pendant"
        for action in scene["actions"]:
            action["start"] += 15
            action["end"] += 15
        for keyframe in scene["camera"]:
            keyframe["time"] += 15
    choice = {
        "finish_reason": "length" if case == "truncated" else "stop",
        "message": {"content": "not JSON" if case == "unreadable" else json.dumps(raw)},
    }
    post = AsyncMock(return_value=httpx.Response(200, json={"choices": [choice]}))
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return await post(*args,**kwargs)
    monkeypatch.setattr(job.httpx,"AsyncClient",lambda **kwargs:Client())
    errors = {
        "truncated": "ran out of space",
        "unreadable": "unreadable response",
        "missing-target": "missing actor or target",
    }
    if case in errors:
        with pytest.raises(job.CartoonJobError, match=errors[case]):
            await job._generate_storyboard("test-only-not-a-key", "A sound at midnight", 15, "2d-cartoon", "hinglish", [])
    else:
        result = await job._generate_storyboard("test-only-not-a-key", "An animated story", 15, "2d-cartoon", "hinglish", [])
        assert result["schema_version"] == 3
        assert result["characters"] and result["scenes"]
        if case == "absolute-time":
            scene = result["scenes"][2]
            assert scene["actions"][1]["target_id"] == "old-pendant"
            assert scene["actions"][1]["start"] == pytest.approx(.5)
            assert scene["camera"][0]["time"] == 0
        files = build_story_project(
            {"duration_seconds": 15, "aspect_ratio": "4:5", "language": "hinglish"},
            result, audio_for(result),
        )
        assert 'data-height="1350"' in files["index.html"]

    post.assert_awaited_once()
    payload = post.await_args.kwargs["json"]
    assert payload["model"] == job.STORY_MODEL
    assert payload["max_tokens"] == 16_384
    assert payload["reasoning"] == {"effort": "low", "exclude": True}
    assert payload["provider"] == {"require_parameters": True}
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_sqlite_ratio_migration_preserves_existing_rows(tmp_path,monkeypatch):
    import aiosqlite
    from types import SimpleNamespace
    from app.services import cartoon_repository as repository
    async with aiosqlite.connect(tmp_path/"ratios.sqlite") as db:
        await db.execute("CREATE TABLE cartoon_projects(id TEXT PRIMARY KEY,user_id TEXT,created_at TEXT,aspect_ratio TEXT CHECK(aspect_ratio IN ('9:16','16:9','1:1')))")
        await db.execute("INSERT INTO cartoon_projects VALUES ('existing','owner','2026-11-20','16:9')")
        async def transaction(callback,**kwargs):
            await callback(db)
        monkeypatch.setattr(repository,"get_settings",lambda:SimpleNamespace(normalized_database_backend="sqlite"))
        monkeypatch.setattr(repository,"run_in_transaction",transaction)
        await repository.init_cartoon_studio()
        await db.execute("INSERT INTO cartoon_projects VALUES ('new','owner','2026-11-21','4:5')")
        rows=await (await db.execute("SELECT id,aspect_ratio FROM cartoon_projects ORDER BY id")).fetchall()
        assert rows==[("existing","16:9"),("new","4:5")]


@pytest.mark.asyncio
async def test_failed_alignment_retry_reuses_paid_speech_instead_of_regenerating(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from app.services import cartoon_story_job as pipeline, cartoon_job as worker, jobs
    from app.core import database
    raw=fixtures()["garden"];raw["characters"][0]["voice_id"]="saved-test-voice"
    updates=[]
    async def execute(sql,args):
        updates.append(json.loads(args[0]))
    async def tts(key,model,voice,text,path):
        path.write_bytes(b"test-audio")
        return []
    speech=AsyncMock(side_effect=tts)
    monkeypatch.setattr(worker,"_tts_audio",speech)
    monkeypatch.setattr(worker,"_probe_audio_duration",AsyncMock(return_value=2))
    monkeypatch.setattr(database,"execute",execute)
    monkeypatch.setattr(jobs,"update_job",AsyncMock())
    monkeypatch.setattr(pipeline,"audio_alignment",AsyncMock(side_effect=StoryValidationError("alignment unavailable")))
    class Storage:
        async def stat(self,key):return SimpleNamespace(size=10)
        async def upload(self,*args,**kwargs):return SimpleNamespace(generation="one")
        async def download(self,key,path,**kwargs):path.write_bytes(b"test-audio")
    project={"id":"fixture","duration_seconds":15,"assets_json":"{}"}
    with pytest.raises(StoryValidationError,match="alignment"):
        await pipeline.run_director_job({"id":"job","user_id":"owner"},project,raw,tmp_path,Storage(),"fake-not-a-key","test-tts")
    assert updates and updates[-1]["scene-1-line-1"]["key"]
    project["assets_json"]=json.dumps(updates[-1])
    with pytest.raises(StoryValidationError,match="alignment"):
        await pipeline.run_director_job({"id":"job","user_id":"owner"},project,raw,tmp_path,Storage(),"fake-not-a-key","test-tts")
    assert speech.await_count==1

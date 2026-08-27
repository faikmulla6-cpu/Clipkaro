from __future__ import annotations

from pathlib import Path

import pytest

from app.services import forced_alignment


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_local_dev_alignment_remains_optional_and_lightweight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(forced_alignment.importlib.util, "find_spec", lambda _: None)
    result = forced_alignment.validate_forced_alignment_runtime("native", False)
    assert result == {"enabled": False, "required": False, "backend": "native"}
    config = _read("backend/app/core/config.py")
    assert 'alignment_backend: str = "native"' in config
    assert "require_forced_alignment: bool = False" in config


def test_production_policy_requires_whisperx_and_forced_alignment() -> None:
    assert forced_alignment.validate_production_alignment_policy("whisperx", True)["required"] is True
    for backend, required in (("native", False), ("native", True), ("whisperx", False)):
        with pytest.raises(RuntimeError, match="Production requires"):
            forced_alignment.validate_production_alignment_policy(backend, required)


def test_whisperx_selection_fails_when_runtime_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(forced_alignment.importlib.util, "find_spec", lambda _: None)
    with pytest.raises(RuntimeError, match="Missing module"):
        forced_alignment.validate_forced_alignment_runtime("whisperx", True)


def test_india_language_alignment_mapping_is_immutable_and_safe() -> None:
    assert forced_alignment.alignment_language("hi") == "hi"
    assert forced_alignment.alignment_language("hinglish") == "hi"
    assert forced_alignment.alignment_language("ur") == "hi"
    assert forced_alignment.alignment_language("mr") == "mr"
    hi = forced_alignment.alignment_model_spec("hi")
    mr = forced_alignment.alignment_model_spec("mr")
    assert hi == {
        "repo_id": "theainerd/Wav2Vec2-large-xlsr-hindi",
        "revision": "062f7f566e2671336992b011dcb9387cd3cffe5e",
    }
    assert mr == {
        "repo_id": "sumedh/wav2vec2-large-xlsr-marathi",
        "revision": "899f3f97fc4d0e6ef6286f35ecf78ee8570ecf9d",
    }
    source = _read("backend/app/services/forced_alignment.py")
    assert 'allow_patterns=["*.json", "*.safetensors"]' in source
    assert "*.bin" not in source


def test_production_runtime_enforces_pinned_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(forced_alignment.importlib.util, "find_spec", lambda _: object())
    versions = {
        "whisperx": forced_alignment.PRODUCTION_WHISPERX_VERSION,
        "faster-whisper": forced_alignment.PRODUCTION_FASTER_WHISPER_VERSION,
    }
    monkeypatch.setattr(forced_alignment.metadata, "version", lambda name: versions[name])
    result = forced_alignment.validate_forced_alignment_runtime(
        "whisperx", True, enforce_production_policy=True, enforce_pinned_versions=True
    )
    assert result["whisperx_version"] == "3.8.6"
    assert result["faster_whisper_version"] == "1.2.1"
    versions["whisperx"] = "9.9.9"
    with pytest.raises(RuntimeError, match="Production requires whisperx"):
        forced_alignment.validate_forced_alignment_runtime(
            "whisperx", True, enforce_production_policy=True, enforce_pinned_versions=True
        )


def test_production_docker_compose_splits_api_asr_from_legacy_whisperx() -> None:
    dockerfile = _read("backend/Dockerfile")
    alignment_requirements = _read("backend/requirements-alignment.txt")
    local_asr_requirements = _read("backend/requirements-local-asr.txt")
    base_requirements = _read("backend/requirements.txt")
    compose = _read("docker-compose.hostinger.yml")
    production_env = _read(".env.production.example")
    # The serverless architecture installs native media tools once in media-base.
    # The production media job and the optional legacy/local-ASR worker both
    # inherit that stage; the API remains lightweight on runtime-base.
    assert "FROM runtime-base AS media-base" in dockerfile
    assert "FROM media-base AS media" in dockerfile
    assert "FROM media-base AS worker" in dockerfile
    assert "FROM runtime-base AS api" in dockerfile
    assert "COPY requirements-local-asr.txt requirements-alignment.txt ./" in dockerfile
    assert "pip install --no-cache-dir -r requirements-alignment.txt" in dockerfile
    assert "whisperx==3.8.6" in alignment_requirements
    assert "torch==2.8.0+cpu" in alignment_requirements
    assert "torchaudio==2.8.0+cpu" in alignment_requirements
    assert "torchvision==0.23.0+cpu" in alignment_requirements
    assert "faster-whisper==1.2.1" in local_asr_requirements
    assert "faster-whisper==1.2.1" not in base_requirements
    assert "target: api" in compose
    assert "ASR_MODE: ${ASR_MODE:-api}" in compose
    assert "GROQ_ASR_MODEL: ${GROQ_ASR_MODEL:-whisper-large-v3}" in compose
    assert "CLOUDFLARE_ASR_MODEL: ${CLOUDFLARE_ASR_MODEL:-@cf/openai/whisper-large-v3-turbo}" in compose
    assert "ASR_MODE=api" in production_env
    assert "GROQ_ASR_MODEL=whisper-large-v3" in production_env
    assert "CLOUDFLARE_ASR_MODEL=@cf/openai/whisper-large-v3-turbo" in production_env


def test_api_and_worker_both_fail_closed_on_bad_production_policy() -> None:
    main = _read("backend/app/main.py")
    worker = _read("backend/app/worker.py")
    assert "validate_production_alignment_policy(" in main
    validation = worker.index("validate_forced_alignment_runtime(")
    database_open = worker.index("await init_db()")
    claim = worker.index("await claim_next_job(worker_id)")
    assert validation < database_open < claim


def test_asr_models_are_released_before_whisperx_alignment_loads() -> None:
    transcription = _read("backend/app/services/transcription.py")
    alignment_branch = transcription.index('if alignment_backend == "whisperx":')
    forced_call = transcription.index("verified = force_align_whisperx", alignment_branch)
    between = transcription[alignment_branch:forced_call]
    assert 'if "secondary" in locals()' in between
    assert "del secondary" in between
    assert 'if "model" in locals()' in between
    assert "del model" in between
    assert "gc.collect()" in between


def test_fresh_launch_qa_builds_exact_api_first_production_images() -> None:
    workflow = _read(".github/workflows/fresh-launch-qa.yml")
    assert "--target api" in workflow
    assert "--target media" in workflow
    assert "--target worker" not in workflow
    assert "media_runtime" in workflow
    assert "production media runtime validated" in workflow
    assert "find_spec('faster_whisper') is None" in workflow
    assert "find_spec('whisperx') is None" in workflow
    assert "--check backend_api_image=" in workflow
    assert "--check backend_media_image=" in workflow
    assert "--check media_runtime=" in workflow


def test_real_asr_verdict_uses_forced_whisperx_profile() -> None:
    workflow = _read(".github/workflows/asr-stress.yml")
    assert "ALIGNMENT_BACKEND: whisperx" in workflow
    assert 'REQUIRE_FORCED_ALIGNMENT: "true"' in workflow
    assert "pip install -r requirements-alignment.txt" in workflow
    assert "validate_forced_alignment_runtime" in workflow

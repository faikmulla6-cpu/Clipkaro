"""WhisperX forced alignment and production runtime validation.

Local/development remains lightweight: PyTorch/WhisperX are not required unless
WhisperX is explicitly selected. The production media worker uses a dedicated
image and fails before taking jobs if policy/runtime versions drift.
"""
from __future__ import annotations

import importlib.util
from importlib import metadata
from pathlib import Path
from typing import Any


PRODUCTION_WHISPERX_VERSION = "3.8.6"
PRODUCTION_FASTER_WHISPER_VERSION = "1.2.1"

# WhisperX ships a Hindi mapping but not Marathi. Pin both India-language model
# snapshots to immutable revisions and materialize only JSON + safetensors files.
ALIGN_MODEL_SPECS: dict[str, dict[str, str]] = {
    "hi": {
        "repo_id": "theainerd/Wav2Vec2-large-xlsr-hindi",
        "revision": "062f7f566e2671336992b011dcb9387cd3cffe5e",
    },
    "mr": {
        "repo_id": "sumedh/wav2vec2-large-xlsr-marathi",
        "revision": "899f3f97fc4d0e6ef6286f35ecf78ee8570ecf9d",
    },
}


def alignment_language(language: str) -> str:
    code = str(language or "").strip().lower()
    return "hi" if code in {"hi", "ur", "hinglish"} else code


def alignment_model_spec(language: str) -> dict[str, str] | None:
    spec = ALIGN_MODEL_SPECS.get(alignment_language(language))
    return dict(spec) if spec else None


def validate_production_alignment_policy(alignment_backend: str, require_forced_alignment: bool) -> dict[str, Any]:
    """Validate production policy without importing the heavy worker runtime."""
    backend = str(alignment_backend or "").strip().lower()
    required = bool(require_forced_alignment)
    if backend != "whisperx" or not required:
        raise RuntimeError(
            "Production requires ALIGNMENT_BACKEND=whisperx and REQUIRE_FORCED_ALIGNMENT=true."
        )
    return {"backend": "whisperx", "required": True}


def validate_forced_alignment_runtime(
    alignment_backend: str,
    require_forced_alignment: bool,
    *,
    enforce_production_policy: bool = False,
    enforce_pinned_versions: bool = False,
) -> dict[str, Any]:
    """Validate alignment selection and, for workers, installed runtime versions."""
    backend = str(alignment_backend or "").strip().lower()
    required = bool(require_forced_alignment)

    if enforce_production_policy or enforce_pinned_versions:
        validate_production_alignment_policy(backend, required)
    elif required and backend != "whisperx":
        raise RuntimeError(
            "Forced alignment is required, but ALIGNMENT_BACKEND is not set to whisperx."
        )

    if backend != "whisperx":
        return {"enabled": False, "required": required, "backend": backend or "native"}

    required_modules = ("torch", "whisperx", "faster_whisper", "huggingface_hub")
    missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError(
            "WhisperX forced alignment is enabled but the worker runtime is incomplete. "
            f"Missing module(s): {', '.join(missing)}. Build the Docker worker target so "
            "requirements-alignment.txt is installed."
        )

    result: dict[str, Any] = {
        "enabled": True,
        "required": required,
        "backend": "whisperx",
        "alignment_models": {
            code: f"{spec['repo_id']}@{spec['revision']}" for code, spec in ALIGN_MODEL_SPECS.items()
        },
    }
    if enforce_pinned_versions:
        try:
            whisperx_version = metadata.version("whisperx")
            faster_whisper_version = metadata.version("faster-whisper")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "WhisperX production package metadata is unavailable in the worker image."
            ) from exc
        if whisperx_version != PRODUCTION_WHISPERX_VERSION:
            raise RuntimeError(
                f"Production requires whisperx=={PRODUCTION_WHISPERX_VERSION}; found {whisperx_version}."
            )
        if faster_whisper_version != PRODUCTION_FASTER_WHISPER_VERSION:
            raise RuntimeError(
                "Production ASR/alignment dependency drift detected: "
                f"requires faster-whisper=={PRODUCTION_FASTER_WHISPER_VERSION}; found {faster_whisper_version}."
            )
        result.update(
            whisperx_version=whisperx_version,
            faster_whisper_version=faster_whisper_version,
        )
    return result


def _materialize_alignment_model(language: str, model_cache_dir: Path) -> str | None:
    spec = alignment_model_spec(language)
    if not spec:
        return None
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Pinned alignment-model download support is unavailable in the media worker."
        ) from exc

    cache_dir = model_cache_dir / "alignment-hub"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        return str(
            snapshot_download(
                repo_id=spec["repo_id"],
                revision=spec["revision"],
                cache_dir=str(cache_dir),
                allow_patterns=["*.json", "*.safetensors"],
            )
        )
    except Exception as exc:
        raise RuntimeError(
            f"Pinned {alignment_language(language)} alignment model could not be materialized: "
            f"{spec['repo_id']}@{spec['revision']}."
        ) from exc


def force_align_whisperx(
    audio_path: Path,
    segments: list[dict[str, Any]],
    language: str,
    model_cache_dir: Path,
) -> list[dict[str, Any]]:
    validate_forced_alignment_runtime("whisperx", True)
    try:
        import torch  # type: ignore
        import whisperx  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "WhisperX forced alignment is enabled but its runtime could not be imported. "
            "Install requirements-alignment.txt on the media worker."
        ) from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    code = alignment_language(language)
    model_name = _materialize_alignment_model(code, model_cache_dir)
    model, metadata_payload = whisperx.load_align_model(
        language_code=code,
        device=device,
        model_name=model_name,
        model_dir=str(model_cache_dir),
    )
    audio = whisperx.load_audio(str(audio_path))
    payload = [
        {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
        for s in segments
    ]
    result = whisperx.align(
        payload,
        model,
        metadata_payload,
        audio,
        device,
        return_char_alignments=False,
    )

    aligned: list[dict[str, Any]] = []
    source = result.get("segments", [])
    for original, item in zip(segments, source):
        words: list[dict[str, Any]] = []
        for word in item.get("words", []):
            if word.get("start") is None or word.get("end") is None or not word.get("word"):
                continue
            start, end = float(word["start"]), float(word["end"])
            if end <= start:
                continue
            words.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": str(word["word"]).strip(),
                    "confidence": round(float(word.get("score", 0)), 3),
                    "forced_aligned": True,
                }
            )
        if words:
            aligned.append(
                {
                    **original,
                    "start": words[0]["start"],
                    "end": words[-1]["end"],
                    "words": words,
                    "alignment_status": "forced_aligned",
                    "alignment_backend": "whisperx",
                }
            )

    if not aligned or sum(len(s["words"]) for s in aligned) < max(4, len(segments)):
        raise RuntimeError(
            "WhisperX alignment produced insufficient timestamped speech; export was blocked."
        )
    return aligned

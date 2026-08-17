#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.asr_benchmark import probe_duration  # noqa: E402
from app.services.video import find_media_tool  # noqa: E402


ARCHIVE_NAME = "Hindi-English_test.tar.gz"
DOWNLOAD_URLS = (
    f"https://openslr.trmal.net/resources/104/{ARCHIVE_NAME}",
    f"https://openslr.elda.org/resources/104/{ARCHIVE_NAME}",
    f"https://openslr.magicdatatech.com/resources/104/{ARCHIVE_NAME}",
)
SOURCE_PAGE = "https://www.openslr.org/104/"
SOURCE_LICENSE = "CC BY-SA 4.0"
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus"}
DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
LATIN_RE = re.compile(r"[A-Za-z]")
MAX_ARCHIVE_BYTES = 700 * 1024 * 1024


def _download(url: str, target: Path) -> None:
    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0, 3.0), start=1):
        if delay:
            time.sleep(delay)
        target.unlink(missing_ok=True)
        try:
            with requests.get(
                url,
                stream=True,
                timeout=(20, 180),
                headers={"User-Agent": "ClipKaro-ASR-Qualification/1.0 (https://clipkaro.pro)"},
            ) as response:
                response.raise_for_status()
                total = 0
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=4 * 1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise RuntimeError("MUCS archive exceeded the 700 MiB safety limit.")
                        handle.write(chunk)
                        if total and total % (100 * 1024 * 1024) < len(chunk):
                            print(f"Downloaded {total / 1024 / 1024:.0f} MiB from {url}", flush=True)
            if target.stat().st_size < 100 * 1024 * 1024:
                raise RuntimeError(
                    f"MUCS archive was unexpectedly small ({target.stat().st_size} bytes); upstream may have changed."
                )
            return
        except Exception as exc:
            last_error = exc
            target.unlink(missing_ok=True)
            print(
                f"MUCS download attempt {attempt}/2 failed for {url}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
    assert last_error is not None
    raise last_error


def _download_from_mirrors(target: Path, preferred_url: str = "") -> str:
    urls: list[str] = []
    if preferred_url.strip():
        urls.append(preferred_url.strip())
    urls.extend(url for url in DOWNLOAD_URLS if url not in urls)
    errors: list[str] = []
    for url in urls:
        print(f"Downloading MUCS Hindi-English test set from {url}", flush=True)
        try:
            _download(url, target)
            return url
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("All MUCS OpenSLR mirrors failed. " + " | ".join(errors))


def _safe_destination(root: Path, member_name: str) -> Path:
    resolved_root = root.resolve()
    destination = (root / member_name).resolve()
    if destination != resolved_root and resolved_root not in destination.parents:
        raise RuntimeError(f"Unsafe archive member path: {member_name}")
    return destination


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, mode="r:*") as tar:
        for member in tar:
            target = _safe_destination(destination, member.name)
            if member.issym() or member.islnk():
                raise RuntimeError(f"MUCS archive contains a link, refusing extraction: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = _safe_destination(destination, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        _safe_extract_tar(archive, destination)
        return
    if name.endswith(".zip"):
        _safe_extract_zip(archive, destination)
        return
    raise RuntimeError(f"Unsupported MUCS archive format: {archive.name}")


def _read_kaldi_text(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            raise RuntimeError(f"Invalid Kaldi text line {path}:{line_number}")
        mapping[parts[0]] = parts[1].strip()
    if not mapping:
        raise RuntimeError(f"Kaldi text file is empty: {path}")
    return mapping


def _read_kaldi_segments(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 4:
            raise RuntimeError(f"Invalid Kaldi segments line {path}:{line_number}")
        utterance_id, recording_id, start_raw, end_raw = parts
        try:
            start = float(start_raw)
            end = float(end_raw)
        except ValueError as exc:
            raise RuntimeError(f"Invalid segment time {path}:{line_number}") from exc
        if start < 0 or end <= start:
            raise RuntimeError(f"Invalid segment range {path}:{line_number}: {start}-{end}")
        rows.append({
            "utterance_id": utterance_id,
            "recording_id": recording_id,
            "start": start,
            "end": end,
            "duration": end - start,
        })
    if not rows:
        raise RuntimeError(f"Kaldi segments file is empty: {path}")
    return rows


def _read_wav_scp(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Invalid wav.scp line {path}:{line_number}")
        mapping[parts[0]] = parts[1].strip()
    if not mapping:
        raise RuntimeError(f"wav.scp is empty: {path}")
    return mapping


def _find_kaldi_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    for segments in root.rglob("segments"):
        if not segments.is_file():
            continue
        parent = segments.parent
        if (parent / "text").is_file() and (parent / "wav.scp").is_file():
            found.append(parent)
    # Prefer test-looking paths, but retain all valid directories as a fallback.
    return sorted(set(found), key=lambda path: ("test" not in path.as_posix().casefold(), path.as_posix()))


def _audio_index(root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for audio in root.rglob("*"):
        if not audio.is_file() or audio.suffix.casefold() not in AUDIO_SUFFIXES:
            continue
        resolved = audio.resolve()
        for key in (audio.name.casefold(), audio.stem.casefold()):
            index.setdefault(key, resolved)
        try:
            relative = audio.relative_to(root).as_posix().casefold()
            index.setdefault(relative, resolved)
        except ValueError:
            pass
    return index


def _wav_scp_path_tokens(spec: str) -> list[str]:
    # We deliberately never execute a wav.scp pipe. We only use path-looking
    # tokens to locate the corresponding media already present in the archive.
    try:
        tokens = shlex.split(spec, posix=True)
    except ValueError:
        tokens = spec.split()
    return [token.strip("'\"") for token in tokens if Path(token.strip("'\"")).suffix.casefold() in AUDIO_SUFFIXES]


def _resolve_recording_audio(
    recording_id: str,
    wav_spec: str,
    index: dict[str, Path],
) -> Path | None:
    candidates = [recording_id]
    candidates.extend(_wav_scp_path_tokens(wav_spec))
    for candidate in candidates:
        normalized = candidate.replace("\\", "/")
        keys = (
            normalized.casefold(),
            Path(normalized).name.casefold(),
            Path(normalized).stem.casefold(),
        )
        for key in keys:
            match = index.get(key)
            if match:
                return match
    return None


def _is_code_switched(text: str) -> bool:
    return bool(DEVANAGARI_RE.search(text) and LATIN_RE.search(text))


def _load_kaldi_utterances(root: Path) -> list[dict[str, Any]]:
    audio = _audio_index(root)
    if not audio:
        raise RuntimeError("MUCS archive contained no supported audio files.")

    utterances: list[dict[str, Any]] = []
    seen: set[str] = set()
    diagnostics: list[str] = []
    for data_dir in _find_kaldi_dirs(root):
        texts = _read_kaldi_text(data_dir / "text")
        segments = _read_kaldi_segments(data_dir / "segments")
        wav_scp = _read_wav_scp(data_dir / "wav.scp")
        resolved_recordings: dict[str, Path | None] = {}
        for segment in segments:
            utt = str(segment["utterance_id"])
            if utt in seen:
                continue
            reference = texts.get(utt, "").strip()
            if len(reference.split()) < 2:
                continue
            recording_id = str(segment["recording_id"])
            if recording_id not in resolved_recordings:
                resolved_recordings[recording_id] = _resolve_recording_audio(
                    recording_id,
                    wav_scp.get(recording_id, recording_id),
                    audio,
                )
            recording = resolved_recordings[recording_id]
            if recording is None:
                continue
            duration = float(segment["duration"])
            if duration < 0.7 or duration > 120:
                continue
            seen.add(utt)
            utterances.append({
                **segment,
                "reference": reference,
                "recording": recording,
                "code_switched": _is_code_switched(reference),
                "kaldi_dir": str(data_dir.relative_to(root)),
            })
        diagnostics.append(
            f"{data_dir.relative_to(root)}: text={len(texts)} segments={len(segments)} "
            f"resolved_recordings={sum(path is not None for path in resolved_recordings.values())}/{len(resolved_recordings)}"
        )

    if not utterances:
        detail = " | ".join(diagnostics) if diagnostics else "no Kaldi data directories found"
        raise RuntimeError(f"Could not resolve any MUCS Kaldi utterances to audio. {detail}")

    # Favor explicit Devanagari+Latin code-switching while keeping deterministic
    # order and a fallback for transcripts whose English technical terms were
    # normalized differently by the corpus.
    utterances.sort(key=lambda row: (not bool(row["code_switched"]), str(row["utterance_id"])))
    code_switched = sum(bool(row["code_switched"]) for row in utterances)
    print(
        f"MUCS resolved utterances={len(utterances)} explicit_code_switched={code_switched}; "
        + " | ".join(diagnostics),
        flush=True,
    )
    return utterances


def _materialize_segment(row: dict[str, Any], output: Path) -> Path:
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to slice MUCS Kaldi segments.")
    start = float(row["start"])
    duration = float(row["duration"])
    command = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(row["recording"]),
        "-t",
        f"{duration:.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output),
    ]
    proc = subprocess.run(command, capture_output=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "Could not slice MUCS segment: " + proc.stderr.decode(errors="ignore")[-800:]
        )
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"MUCS segment produced invalid audio: {row['utterance_id']}")
    return output


def _combine(inputs: Iterable[Path], output: Path) -> None:
    items = list(inputs)
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to build the benchmark corpus.")
    command = [ffmpeg, "-nostdin", "-y"]
    for item in items:
        command.extend(["-i", str(item)])
    filters, labels = [], []
    for index in range(len(items)):
        label = f"a{index}"
        filters.append(f"[{index}:a]aresample=16000,aformat=channel_layouts=mono[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"concat=n={len(items)}:v=0:a=1[out]")
    command.extend([
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(output),
    ])
    proc = subprocess.run(command, capture_output=True, timeout=240, check=False)
    if proc.returncode != 0:
        raise RuntimeError("Could not concatenate MUCS samples: " + proc.stderr.decode(errors="ignore")[-800:])


def _build_cases(
    utterances: list[dict[str, Any]],
    output_dir: Path,
    cases: int,
    min_seconds: float,
    workdir: Path,
) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []
    cursor = 0
    used_ids: set[str] = set()
    while len(built) < cases and cursor < len(utterances):
        clips: list[Path] = []
        references: list[str] = []
        source_ids: list[str] = []
        recordings: set[str] = set()
        seconds = 0.0
        explicit_code_switch = 0
        while cursor < len(utterances) and (seconds < min_seconds or len(clips) < 3):
            row = utterances[cursor]
            cursor += 1
            utterance_id = str(row["utterance_id"])
            if utterance_id in used_ids:
                continue
            clip = workdir / f"segment-{len(used_ids):04d}.wav"
            try:
                _materialize_segment(row, clip)
                actual = probe_duration(clip)
            except Exception as exc:
                print(
                    f"Skipping MUCS utterance {utterance_id}: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                clip.unlink(missing_ok=True)
                continue
            if actual < 0.5:
                clip.unlink(missing_ok=True)
                continue
            used_ids.add(utterance_id)
            clips.append(clip)
            references.append(str(row["reference"]))
            source_ids.append(utterance_id)
            recordings.add(Path(row["recording"]).name)
            seconds += actual
            explicit_code_switch += int(bool(row["code_switched"]))
            if len(clips) >= 12:
                break

        if seconds < min_seconds:
            for clip in clips:
                clip.unlink(missing_ok=True)
            break

        number = len(built) + 1
        rel = Path("cases") / f"mucs-hinglish-{number:02d}.m4a"
        target = output_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        _combine(clips, target)
        built.append({
            "id": f"mucs-hinglish-{number:02d}",
            "path": rel.as_posix(),
            "reference": " ".join(references),
            "language": "hinglish",
            "language_hint": "auto",
            "accent": "India",
            "source": "MUCS 2021 Hindi-English test set (Kaldi segments)",
            "source_url": SOURCE_PAGE,
            "license": SOURCE_LICENSE,
            "source_utterances": len(clips),
            "explicit_code_switched_utterances": explicit_code_switch,
            "source_recordings": sorted(recordings),
            "source_utterance_ids": source_ids,
            "clean_duration_seconds": round(probe_duration(target), 3),
        })
        for clip in clips:
            clip.unlink(missing_ok=True)

    if len(built) < cases:
        raise RuntimeError(f"Only built {len(built)}/{cases} Hinglish benchmark cases.")
    return built


def _merge_manifest(manifest_path: Path, cases: list[dict[str, Any]], download_url: str) -> None:
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {"schema_version": 1, "cases": payload}
    else:
        payload = {"schema_version": 1, "cases": []}
    existing = [
        row for row in payload.get("cases", [])
        if not str(row.get("id", "")).startswith("mucs-hinglish-")
    ]
    payload["cases"] = existing + cases
    payload.setdefault("sources", {})["mucs_hindi_english"] = {
        "source_page": SOURCE_PAGE,
        "download": download_url,
        "mirrors": list(DOWNLOAD_URLS),
        "license": SOURCE_LICENSE,
        "format": "Kaldi text + segments + wav.scp",
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import real Hindi-English MUCS speech into the ClipKaro ASR qualification corpus."
    )
    parser.add_argument("--output-dir", default="stress_corpus")
    parser.add_argument(
        "--archive",
        default="",
        help="Existing Hindi-English_test.tar.gz (or legacy ZIP). If omitted, downloads from OpenSLR mirrors.",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Optional preferred archive URL; official OpenSLR mirrors are attempted after it.",
    )
    parser.add_argument("--cases", type=int, default=3)
    parser.add_argument("--min-seconds", type=float, default=32.0)
    args = parser.parse_args()
    if args.cases < 2:
        raise SystemExit("Use at least 2 Hinglish cases for qualification.")
    if args.min_seconds < 22:
        raise SystemExit("Cases must exceed ClipKaro's 20-second reliable-speech gate.")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    download_url = "local archive"
    with tempfile.TemporaryDirectory(prefix="clipkaro-mucs-") as temp:
        tempdir = Path(temp)
        if args.archive:
            archive = Path(args.archive).resolve()
            if not archive.exists():
                raise FileNotFoundError(archive)
        else:
            archive = tempdir / ARCHIVE_NAME
            download_url = _download_from_mirrors(archive, args.url)

        extracted = tempdir / "extracted"
        _safe_extract(archive, extracted)
        kaldi_dirs = _find_kaldi_dirs(extracted)
        if not kaldi_dirs:
            raise RuntimeError(
                "MUCS archive has no Kaldi directory containing text, segments and wav.scp. "
                "The upstream archive layout may have changed."
            )
        print(
            "MUCS Kaldi directories: " + ", ".join(str(path.relative_to(extracted)) for path in kaldi_dirs),
            flush=True,
        )
        utterances = _load_kaldi_utterances(extracted)
        segment_workdir = tempdir / "segments"
        segment_workdir.mkdir()
        built = _build_cases(utterances, output_dir, args.cases, args.min_seconds, segment_workdir)

    manifest_path = output_dir / "manifest.json"
    _merge_manifest(manifest_path, built, download_url)
    print(
        f"Added {len(built)} genuine Hinglish cases to {manifest_path}; language_hint=auto; "
        "references were aligned from MUCS Kaldi segments.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.asr_benchmark import probe_duration  # noqa: E402
from app.services.video import find_media_tool  # noqa: E402


DATASET = "google/fleurs"
DATASET_LICENSE = "CC BY 4.0"
DATASET_URL = "https://huggingface.co/datasets/google/fleurs"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
HUB_PARQUET_URL = f"https://huggingface.co/api/datasets/{DATASET}/parquet"
LANGUAGES = {
    "hi_in": {"language": "hi", "language_hint": "auto", "label": "Hindi (India)"},
    "mr_in": {"language": "mr", "language_hint": "auto", "label": "Marathi (India)"},
}


def _rows_from_dataset_server(config: str, offset: int, length: int) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0, 2.0, 6.0), start=1):
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(
                ROWS_URL,
                params={
                    "dataset": DATASET,
                    "config": config,
                    "split": "test",
                    "offset": offset,
                    "length": length,
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("rows") or []
            if not rows:
                raise RuntimeError(f"FLEURS dataset viewer returned no rows for {config}.")
            normalized = [item.get("row") or {} for item in rows]
            for row in normalized:
                row["_clipkaro_acquisition"] = "datasets-server/rows"
            return normalized
        except Exception as exc:
            last_error = exc
            print(
                f"FLEURS rows API attempt {attempt}/3 failed for {config}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
    assert last_error is not None
    raise last_error


def _rows_from_raw_hub_archive(
    config: str,
    offset: int,
    length: int,
    workspace: Path,
) -> list[dict[str, Any]]:
    """Download FLEURS' canonical test TSV + compressed audio archive.

    This is deliberately sequential and uses Hugging Face's Hub/Xet downloader,
    avoiding both datasets-server and random remote Parquet range reads. The TSV
    format is the upstream FLEURS loader's seven-column schema:
    id, file_name, raw_transcription, transcription, tokens, num_samples, gender.
    Only the requested audio members are materialized from the tarball.
    """
    print(f"FLEURS raw fallback downloading canonical assets for {config}", flush=True)
    tsv = Path(hf_hub_download(
        repo_id=DATASET,
        repo_type="dataset",
        filename=f"data/{config}/test.tsv",
    ))
    archive = Path(hf_hub_download(
        repo_id=DATASET,
        repo_type="dataset",
        filename=f"data/{config}/audio/test.tar.gz",
    ))

    parsed: list[dict[str, Any]] = []
    with tsv.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 7:
                raise RuntimeError(
                    f"Unexpected FLEURS TSV schema for {config} at line {line_number}: {len(parts)} columns"
                )
            _id, file_name, raw_transcription, transcription, _tokens, num_samples, gender = parts
            parsed.append({
                "id": int(_id),
                "path": file_name,
                "raw_transcription": raw_transcription,
                "transcription": transcription,
                "num_samples": int(num_samples),
                "gender": gender,
            })

    selected = parsed[offset: offset + length]
    if not selected:
        raise RuntimeError(f"FLEURS raw TSV returned no requested rows for {config}.")

    audio_dir = workspace / f"raw-{config}"
    audio_dir.mkdir(parents=True, exist_ok=True)
    needed = {str(row["path"]): row for row in selected}
    found: set[str] = set()

    # Stream through the compressed archive once and materialize only selected
    # basenames. extractfile() avoids archive path traversal entirely.
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            basename = Path(member.name).name
            if basename not in needed or basename in found:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            destination = audio_dir / basename
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if destination.stat().st_size < 1024:
                destination.unlink(missing_ok=True)
                continue
            found.add(basename)
            if len(found) == len(needed):
                break

    missing = sorted(set(needed) - found)
    if missing:
        raise RuntimeError(
            f"FLEURS raw archive did not contain {len(missing)} selected files for {config}: "
            + ", ".join(missing[:5])
        )

    rows: list[dict[str, Any]] = []
    for row in selected:
        filename = str(row["path"])
        rows.append({
            **row,
            "audio": {"path": str((audio_dir / filename).resolve())},
            "_clipkaro_acquisition": "huggingface-hub/raw-tsv+tar+xet",
        })
    return rows


def _rows_from_hub_parquet(config: str, offset: int, length: int) -> list[dict[str, Any]]:
    """Last-resort Hub Parquet reader after both canonical paths fail."""
    try:
        import fsspec
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "FLEURS Hub-Parquet fallback requires pyarrow and fsspec[http]."
        ) from exc

    urls_response = requests.get(f"{HUB_PARQUET_URL}/{config}/test", timeout=60)
    urls_response.raise_for_status()
    urls = urls_response.json()
    if not isinstance(urls, list) or not urls:
        raise RuntimeError(f"Hugging Face Hub returned no FLEURS Parquet test shards for {config}.")

    wanted_end = offset + length
    seen = 0
    selected: list[dict[str, Any]] = []
    columns = ["audio", "transcription", "raw_transcription"]
    for parquet_url in urls:
        print(f"FLEURS last-resort Parquet reader for {config}: {parquet_url}", flush=True)
        with fsspec.open(str(parquet_url), "rb", block_size=8 * 1024 * 1024) as remote:
            parquet = pq.ParquetFile(remote)
            for batch in parquet.iter_batches(batch_size=max(16, min(64, length)), columns=columns):
                for row in batch.to_pylist():
                    if seen >= wanted_end:
                        return selected
                    if seen >= offset:
                        row["_clipkaro_acquisition"] = "huggingface-hub/parquet"
                        selected.append(row)
                    seen += 1
                    if len(selected) >= length:
                        return selected
    if not selected:
        raise RuntimeError(f"FLEURS Hub-Parquet fallback returned no rows for {config}.")
    return selected


def _rows(config: str, offset: int, length: int, workspace: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    try:
        return _rows_from_dataset_server(config, offset, length)
    except Exception as exc:
        errors.append(f"rows={type(exc).__name__}: {exc}")
        print(
            f"FLEURS datasets-server unavailable for {config}; switching to canonical raw Hub assets",
            file=sys.stderr,
            flush=True,
        )

    try:
        return _rows_from_raw_hub_archive(config, offset, length, workspace)
    except Exception as exc:
        errors.append(f"raw={type(exc).__name__}: {exc}")
        print(
            f"FLEURS raw Hub assets failed for {config}; attempting last-resort Parquet: {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )

    try:
        return _rows_from_hub_parquet(config, offset, length)
    except Exception as exc:
        errors.append(f"parquet={type(exc).__name__}: {exc}")
        raise RuntimeError(
            f"All FLEURS acquisition paths failed for {config}. " + " | ".join(errors)
        ) from exc


def _transcript(row: dict[str, Any]) -> str:
    return str(row.get("transcription") or row.get("raw_transcription") or "").strip()


def _download(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, timeout=90) as response:
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if chunk:
                    handle.write(chunk)
    if destination.stat().st_size < 1024:
        raise RuntimeError("Downloaded FLEURS audio was unexpectedly small.")


def _materialize_audio(row: dict[str, Any], destination: Path) -> None:
    audio = row.get("audio")
    if not isinstance(audio, dict):
        raise RuntimeError("FLEURS row has no audio object.")

    local_path = str(audio.get("path") or "").strip()
    if local_path:
        source = Path(local_path)
        if not source.exists() or source.stat().st_size < 1024:
            raise RuntimeError(f"FLEURS local audio path is missing/invalid: {source}")
        shutil.copyfile(source, destination)
        return

    embedded = audio.get("bytes")
    if isinstance(embedded, memoryview):
        embedded = embedded.tobytes()
    if isinstance(embedded, bytearray):
        embedded = bytes(embedded)
    if isinstance(embedded, bytes) and embedded:
        destination.write_bytes(embedded)
        if destination.stat().st_size < 1024:
            raise RuntimeError("Embedded FLEURS audio was unexpectedly small.")
        return

    url = str(audio.get("src") or audio.get("url") or "").strip()
    if url:
        _download(url, destination)
        return
    raise RuntimeError("FLEURS row exposed no local path, embedded audio bytes, or downloadable URL.")


def _combine(inputs: list[Path], output: Path) -> None:
    ffmpeg = find_media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to build the benchmark corpus.")
    command = [ffmpeg, "-nostdin", "-y"]
    for item in inputs:
        command.extend(["-i", str(item)])
    filters = []
    labels = []
    for index in range(len(inputs)):
        label = f"a{index}"
        filters.append(f"[{index}:a]aresample=16000,aformat=channel_layouts=mono[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"concat=n={len(inputs)}:v=0:a=1[out]")
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[out]",
        "-c:a", "aac", "-b:a", "96k", str(output),
    ])
    proc = subprocess.run(command, capture_output=True, timeout=180, check=False)
    if proc.returncode != 0:
        raise RuntimeError("Could not concatenate FLEURS samples: " + proc.stderr.decode(errors="ignore")[-700:])


def _build_language_cases(config: str, output_dir: Path, cases: int, min_seconds: float) -> list[dict[str, Any]]:
    meta = LANGUAGES[config]
    built: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"fleurs-{config}-") as temp:
        tempdir = Path(temp)
        # Request enough deterministic rows to build multiple >=20-second cases.
        source_rows = _rows(config, 0, min(400, max(240, cases * 10)), tempdir)
        acquisition_paths = sorted({str(row.get("_clipkaro_acquisition") or "unknown") for row in source_rows})
        print(f"FLEURS {config} acquisition={','.join(acquisition_paths)} rows={len(source_rows)}", flush=True)
        cursor = 0
        while len(built) < cases and cursor < len(source_rows):
            clips: list[Path] = []
            references: list[str] = []
            raw_references: list[str] = []
            source_ids: list[str] = []
            source_hashes: list[str] = []
            total_duration = 0.0
            while cursor < len(source_rows) and (total_duration < min_seconds or len(clips) < 3):
                row = source_rows[cursor]
                cursor += 1
                reference = _transcript(row)
                if not reference:
                    continue
                clip = tempdir / f"selected-{cursor:03d}.audio"
                try:
                    _materialize_audio(row, clip)
                    duration = probe_duration(clip)
                except Exception as exc:
                    print(
                        f"Skipping unreadable FLEURS {config} row {cursor}: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    clip.unlink(missing_ok=True)
                    continue
                clips.append(clip)
                references.append(reference)
                raw_references.append(str(row.get("raw_transcription") or reference).strip())
                source_ids.append(str(row.get("id") or row.get("path") or f"{config}-{cursor}"))
                source_hashes.append(hashlib.sha256(clip.read_bytes()).hexdigest())
                total_duration += duration
                if len(clips) >= 6:
                    break
            if total_duration < min_seconds:
                break
            case_number = len(built) + 1
            rel = Path("cases") / f"{config}-{case_number:02d}.m4a"
            target = output_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _combine(clips, target)
            built.append({
                "id": f"{config}-{case_number:02d}",
                "path": rel.as_posix(),
                "reference": " ".join(references),
                "raw_reference": " ".join(raw_references),
                "normalized_reference": " ".join(references),
                "language": meta["language"],
                "language_hint": meta["language_hint"],
                "accent": "India",
                "source": f"FLEURS {meta['label']} test split",
                "source_url": DATASET_URL,
                "license": DATASET_LICENSE,
                "acquisition": acquisition_paths,
                "source_utterances": len(clips),
                "source_clip_ids": source_ids,
                "source_audio_sha256": source_hashes,
                "dataset": DATASET,
                "config": config,
                "split": "test",
                "clean_duration_seconds": round(probe_duration(target), 3),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            })
            for clip in clips:
                clip.unlink(missing_ok=True)
    if len(built) < cases:
        raise RuntimeError(f"Only built {len(built)}/{cases} {config} benchmark cases.")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a small reproducible FLEURS Hindi/Marathi ASR stress corpus.")
    parser.add_argument("--output-dir", default="stress_corpus")
    parser.add_argument("--cases-per-language", type=int, default=3)
    parser.add_argument("--min-seconds", type=float, default=32.0)
    args = parser.parse_args()
    if args.cases_per_language < 2:
        raise SystemExit("Use at least 2 cases per language for useful distribution metrics.")
    if args.min_seconds < 22:
        raise SystemExit("Cases must exceed ClipKaro's 20-second reliable-speech gate.")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    for config in LANGUAGES:
        print(f"Fetching {config}…", flush=True)
        cases.extend(_build_language_cases(config, output_dir, args.cases_per_language, args.min_seconds))

    manifest_path = output_dir / "manifest.json"
    existing: dict[str, Any] = {}
    if manifest_path.exists():
        try: existing = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
        except Exception: existing = {}
    retained = [row for row in existing.get("cases", []) if str(row.get("language")) not in {"hi", "mr"}]
    manifest = {
        "schema_version": 1,
        "dataset": DATASET,
        "dataset_url": DATASET_URL,
        "dataset_license": DATASET_LICENSE,
        "notes": (
            "FLEURS supplies real Hindi and Marathi speech. Qualification uses language_hint=auto. "
            "Acquisition retries datasets-server, then uses canonical TSV+audio tarballs through the Hub/Xet downloader, "
            "with remote Parquet retained only as a last resort."
        ),
        "cases": retained + cases,
    }
    manifest_path.write_text(__import__("json").dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

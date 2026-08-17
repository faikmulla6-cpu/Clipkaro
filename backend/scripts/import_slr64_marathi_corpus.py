#!/usr/bin/env python3
"""Create the deterministic Marathi clean set from official OpenSLR SLR64."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.services.asr_benchmark import normalize_text, probe_duration  # noqa: E402

BASE = "https://openslr.trmal.net/resources/64"
ARCHIVE = "mr_in_female.zip"
LICENSE = "CC BY-SA 4.0"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch(url: str, destination: Path, *, resumable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        offset = partial.stat().st_size if resumable and partial.exists() else 0
        headers = {"User-Agent": "ClipKaro-ASR-Qualification/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=90) as source:
                # A server that ignores Range must not be appended to a partial.
                append = offset > 0 and getattr(source, "status", 200) == 206
                if offset and not append:
                    partial.unlink(missing_ok=True)
                with partial.open("ab" if append else "wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            if partial.stat().st_size < 1024:
                raise RuntimeError(f"Unexpectedly small download: {url}")
            partial.replace(destination)
            return
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Download failed after 3 bounded attempts: {type(last_error).__name__}: {last_error}")


def stable_rows(index: Path, count: int) -> list[tuple[str, str]]:
    rows = []
    for line in index.read_text(encoding="utf-8").splitlines():
        clip, text = line.split("\t", 1)
        if text.strip(): rows.append((clip.strip(), text.strip()))
    # Hash order prevents choosing hand-picked/easy samples, while retaining a
    # reproducible list tied to the official line index.
    rows.sort(key=lambda row: hashlib.sha256(row[0].encode("utf-8")).hexdigest())
    return rows[:count]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "stress_corpus")
    parser.add_argument("--archive-dir", type=Path, default=ROOT.parent.parent.parent / "ClipKaro_ASR_Source_Archives")
    args = parser.parse_args()
    corpus = args.output_dir; source = args.archive_dir
    index = source / "SLR64-line_index.tsv"; license_path = source / "SLR64-LICENSE"
    if not index.exists(): fetch(f"{BASE}/line_index.tsv", index)
    if not license_path.exists(): fetch(f"{BASE}/LICENSE", license_path)
    if "Attribution-ShareAlike 4.0 International" not in license_path.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError("SLR64 license verification failed; refusing acquisition.")
    selected = stable_rows(index, 30)
    if len(selected) != 30: raise RuntimeError("SLR64 index did not contain 30 usable rows.")
    archive = source / ARCHIVE
    if not archive.exists():
        print(f"Downloading official SLR64 archive to {archive}", flush=True)
        fetch(f"{BASE}/{ARCHIVE}", archive, resumable=True)
    if not zipfile.is_zipfile(archive): raise RuntimeError("SLR64 archive is not a valid ZIP.")
    with zipfile.ZipFile(archive) as zipped:
        names = {Path(name).stem: name for name in zipped.namelist() if name.lower().endswith(".wav")}
        missing = [clip for clip, _ in selected if clip not in names]
        if missing: raise RuntimeError(f"SLR64 archive misses selected clips: {missing[:3]}")
        cases = []
        for ordinal, (clip, reference) in enumerate(selected, 1):
            case_id = f"slr64-mr-{ordinal:02d}"; target = corpus / "cases" / f"{case_id}.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                partial = target.with_suffix(".partial")
                with zipped.open(names[clip]) as incoming, partial.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
                partial.replace(target)
            duration = probe_duration(target)
            if duration <= 0: raise RuntimeError(f"Unreadable SLR64 media: {clip}")
            cases.append({"id": case_id, "path": f"cases/{target.name}", "language": "mr", "language_hint": "mr", "scenario": "clean",
                "source": "OpenSLR SLR64 Marathi test corpus", "dataset": "OpenSLR/SLR64", "split": "published corpus", "license": LICENSE,
                "upstream_clip_id": clip, "duration": duration, "sha256": sha256_file(target), "reference": reference,
                "raw_reference": reference, "normalized_reference": normalize_text(reference), "source_index_sha256": sha256_file(index),
                "source_archive_sha256": sha256_file(archive)})
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"schema_version": 2, "cases": []}
    manifest["cases"] = [case for case in manifest.get("cases", []) if case.get("language") != "mr"] + cases
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected": len(cases), "archive_bytes": archive.stat().st_size, "archive_sha256": sha256_file(archive)}, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())

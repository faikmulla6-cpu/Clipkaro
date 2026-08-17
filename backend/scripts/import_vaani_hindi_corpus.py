#!/usr/bin/env python3
"""Import a deterministic, resumable Hindi qualification slice from Vaani.

This is intentionally an acquisition tool, not an ASR benchmark.  Selection is
made solely from published Vaani metadata and never from provider output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from datasets import Audio, load_dataset
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.asr_benchmark import normalize_text, probe_duration  # noqa: E402

DATASET = "ARTPARK-IISc/Vaani-Benchmark-V1.0"
SPLIT = "test"
LICENSE = "CC BY 4.0"
DEFAULT_REVISION = "0758fa9eba1413d521137225e8390e9c6881c613"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def score(row: dict[str, Any]) -> str:
    # Stable and independent from transcriptions/ASR quality.
    material = "|".join(str(row.get(key, "")) for key in ("speakerID", "gender", "state", "district", "duration", "row_index"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def plan_rows(rows: list[dict[str, Any]], wanted: int) -> list[dict[str, Any]]:
    """Prefer separate speakers, then location/gender groups, deterministically."""
    ordered = sorted(rows, key=score)
    selected: list[dict[str, Any]] = []
    seen_speakers: set[str] = set()
    seen_groups: set[tuple[str, str, str]] = set()
    for row in ordered:
        speaker = str(row.get("speakerID", ""))
        group = (str(row.get("gender", "")), str(row.get("state", "")), str(row.get("district", "")))
        if speaker not in seen_speakers and group not in seen_groups:
            selected.append(row); seen_speakers.add(speaker); seen_groups.add(group)
        if len(selected) == wanted:
            return selected
    for row in ordered:
        if row not in selected:
            selected.append(row)
        if len(selected) == wanted:
            return selected
    raise RuntimeError(f"Only {len(selected)} Hindi rows were available; need {wanted}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "stress_corpus")
    parser.add_argument("--cases", type=int, default=30)
    parser.add_argument("--scan-limit", type=int, default=300, help="bounded metadata scan; no full split download")
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    args = parser.parse_args()
    if args.cases != 30:
        raise SystemExit("The permanent qualification corpus requires exactly 30 Hindi cases.")

    observed = HfApi().dataset_info(DATASET, revision=args.revision, token=True)
    if observed.sha != args.revision:
        raise RuntimeError(f"Unexpected Vaani revision: {observed.sha}; expected {args.revision}")
    corpus = args.output_dir
    state_path = corpus / "acquisition-vaani-hindi.json"
    state = read_json(state_path, {"dataset": DATASET, "revision": args.revision, "planned": [], "downloaded": [], "failures": []})
    if state.get("revision") != args.revision:
        raise RuntimeError("Existing Vaani acquisition state is pinned to another revision.")

    if not state["planned"]:
        stream = load_dataset(DATASET, split=SPLIT, streaming=True, revision=args.revision, token=True).cast_column("audio", Audio(decode=False))
        candidates: list[dict[str, Any]] = []
        for index, item in enumerate(stream):
            if index >= args.scan_limit:
                break
            if str(item.get("language", "")).strip().casefold() != "hindi":
                continue
            candidates.append({
                "row_index": index, "speakerID": item.get("speakerID"), "gender": item.get("gender"),
                "state": item.get("state"), "district": item.get("district"), "duration": item.get("duration"),
            })
        if len(candidates) < args.cases:
            raise RuntimeError(f"Only {len(candidates)} Hindi candidates in the bounded scan.")
        state["planned"] = plan_rows(candidates, args.cases)
        write_json(state_path, state)

    planned_by_index = {int(row["row_index"]): row for row in state["planned"]}
    complete = {int(row["row_index"]) for row in state["downloaded"]}
    needed = set(planned_by_index) - complete
    if needed:
        stream = load_dataset(DATASET, split=SPLIT, streaming=True, revision=args.revision, token=True).cast_column("audio", Audio(decode=False))
        for index, item in enumerate(stream):
            if index > max(needed):
                break
            if index not in needed:
                continue
            raw = item["audio"].get("bytes") or b""
            if not raw:
                raise RuntimeError(f"Vaani row {index} did not contain audio bytes.")
            case_id = f"vaani-hi-{len(state['downloaded']) + 1:02d}"
            target = corpus / "cases" / f"{case_id}.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".partial")
            temporary.write_bytes(raw)
            try:
                duration = probe_duration(temporary)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            if duration <= 0:
                temporary.unlink(missing_ok=True); raise RuntimeError(f"Vaani row {index} has zero duration.")
            os.replace(temporary, target)
            refs = {key: str(item.get(key) or "").strip() for key in ("transcription_v1", "transcription_v2", "transcription_v3")}
            if not all(refs.values()):
                raise RuntimeError(f"Vaani row {index} has an empty official reference.")
            state["downloaded"].append({
                "id": case_id, "row_index": index, "audio_path": f"cases/{target.name}", "audio_sha256": digest(raw),
                "duration": duration, "speakerID": item.get("speakerID"), "gender": item.get("gender"), "state": item.get("state"),
                "district": item.get("district"), "language": item.get("language"), "references": refs,
            })
            write_json(state_path, state)
    if len(state["downloaded"]) != args.cases:
        raise RuntimeError("Vaani import incomplete; resume will only fetch missing rows.")

    manifest_path = corpus / "manifest.json"
    manifest = read_json(manifest_path, {"schema_version": 2, "cases": []})
    retained = [case for case in manifest.get("cases", []) if case.get("language") != "hi"]
    hindi_cases = []
    for row in sorted(state["downloaded"], key=lambda value: value["id"]):
        raw_refs = row["references"]
        hindi_cases.append({
            "id": row["id"], "path": row["audio_path"], "language": "hi", "language_hint": "hi", "scenario": "clean",
            "source": "Vaani Benchmark V1.0 test split", "dataset": DATASET, "split": SPLIT, "revision": args.revision,
            "license": LICENSE, "upstream_row_index": row["row_index"], "speaker_id": row["speakerID"], "gender": row["gender"],
            "state": row["state"], "district": row["district"], "duration": row["duration"], "sha256": row["audio_sha256"],
            "reference": raw_refs["transcription_v1"], "raw_references": raw_refs,
            "normalized_references": {key: normalize_text(value) for key, value in raw_refs.items()},
            "reference_policy": "Future scoring takes the deterministic minimum WER/CER across the three independent official Vaani references.",
        })
    manifest["schema_version"] = 2
    manifest["cases"] = retained + hindi_cases
    write_json(manifest_path, manifest)
    print(json.dumps({"revision": args.revision, "planned": len(state["planned"]), "downloaded": len(state["downloaded"]), "manifest": str(manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

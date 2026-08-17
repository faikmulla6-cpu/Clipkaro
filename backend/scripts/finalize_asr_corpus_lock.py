#!/usr/bin/env python3
"""Freeze and verify the permanent ClipKaro real-ASR qualification corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.services.asr_benchmark import normalize_text, probe_duration  # noqa: E402

EXPECTED_THRESHOLD = "4f5e49ab72cebcf51c58b4f83204b1d9a29e0c607c6b19b5c324806b61f9347e"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def normalize_clean(corpus: Path, case: dict[str, Any]) -> dict[str, Any]:
    path = corpus / case["path"]
    actual = sha256_file(path)
    if case.get("sha256") and case["sha256"] != actual:
        raise RuntimeError(f"Hash mismatch for clean case {case['id']}")
    if not str(case.get("reference") or "").strip():
        raise RuntimeError(f"Missing reference for clean case {case['id']}")
    case["sha256"] = actual
    case["duration"] = probe_duration(path)
    case.setdefault("scenario", "clean")
    case.setdefault("normalized_reference", normalize_text(case["reference"]))
    case.setdefault("source_identifier", case.get("upstream_clip_id") or case.get("upstream_row_index") or case.get("source_utterance_ids"))
    # Retain the original SLR104 archive identity alongside the extracted
    # Hinglish segments; this is provenance only and never changes its text.
    if case.get("language") == "hinglish" and not case.get("source_archive_sha256"):
        archive = ROOT.parent.parent.parent / "ClipKaro_ASR_Source_Archives" / "Hindi-English_test.tar.gz"
        if not archive.exists():
            raise RuntimeError("Cannot lock Hinglish provenance: SLR104 source archive is unavailable.")
        case["source_archive_sha256"] = sha256_file(archive)
    return case


def build_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    fields = ("id", "language", "language_hint", "scenario", "path", "audio_path", "sha256", "audio_sha256", "duration", "reference", "normalized_reference", "raw_reference", "raw_references", "normalized_references", "dataset", "source", "source_identifier", "upstream_clip_id", "upstream_row_index", "source_utterance_ids", "license", "revision", "source_archive_sha256", "source_index_sha256", "stress_settings", "settings")
    def select(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{field: row[field] for field in fields if field in row} for row in sorted(rows, key=lambda row: row["id"])]
    return {"lock_version": 1, "normalization": {"function": "app.services.asr_benchmark.normalize_text", "unicode": "NFKC", "casefold": True, "token_regex": "[\\w\\u0900-\\u097f]+"},
        "threshold_hash": EXPECTED_THRESHOLD, "stress_generation": manifest.get("stress_generation"), "street_noise": manifest.get("street_noise"),
        "clean_cases": select(manifest["cases"]), "stress_cases": select(manifest["stress_cases"]), "negative_controls": select(manifest["negative_controls"])}


def verify(corpus: Path, lock: dict[str, Any]) -> dict[str, Any]:
    payload = lock.get("payload") or {}
    actual_lock = hashlib.sha256(canonical(payload)).hexdigest()
    if actual_lock != lock.get("CORPUS_LOCK_SHA256"):
        raise RuntimeError("Corpus lock canonical payload hash does not match.")
    for kind, path_field, hash_field in (("clean_cases", "path", "sha256"), ("stress_cases", "audio_path", "audio_sha256"), ("negative_controls", "audio_path", "audio_sha256")):
        for item in payload.get(kind, []):
            path = corpus / item[path_field]
            if not path.exists() or sha256_file(path) != item[hash_field] or probe_duration(path) <= 0:
                raise RuntimeError(f"Locked {kind} media verification failed: {item['id']}")
    counts = Counter(item["language"] for item in payload["clean_cases"])
    if counts != {"hi": 30, "mr": 30, "hinglish": 30}:
        raise RuntimeError(f"Unexpected clean language counts: {dict(counts)}")
    if len(payload["stress_cases"]) != 810 or len(payload["negative_controls"]) != 3:
        raise RuntimeError("Stress/control coverage is incomplete.")
    return {"CORPUS_LOCK_SHA256": actual_lock, "clean": sum(counts.values()), "stress": 810, "negative_controls": 3}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(); corpus = ROOT / "stress_corpus"; manifest_path = corpus / "manifest.json"; lock_path = corpus / "corpus-lock.json"
    threshold = json.loads((ROOT / "asr-threshold-lock.json").read_text(encoding="utf-8")).get("threshold_sha256")
    if threshold != EXPECTED_THRESHOLD: raise RuntimeError("Frozen ASR threshold hash changed; refusing corpus finalization.")
    if args.verify:
        print(json.dumps(verify(corpus, json.loads(lock_path.read_text(encoding="utf-8"))), ensure_ascii=False)); return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cases"] = [normalize_clean(corpus, dict(case)) for case in manifest.get("cases", [])]
    if Counter(case.get("language") for case in manifest["cases"]) != {"hi": 30, "mr": 30, "hinglish": 30}: raise RuntimeError("Clean corpus is not 30 Hindi + 30 Marathi + 30 Hinglish.")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = build_payload(manifest); lock_hash = hashlib.sha256(canonical(payload)).hexdigest()
    lock = {"CORPUS_LOCK_SHA256": lock_hash, "payload": payload}
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(verify(corpus, lock), ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())

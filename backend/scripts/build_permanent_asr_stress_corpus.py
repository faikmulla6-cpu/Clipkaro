#!/usr/bin/env python3
"""Materialize deterministic stress fixtures and negative controls for the locked corpus."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.services.asr_benchmark import STRESS_SCENARIOS, create_stress_variant, probe_duration  # noqa: E402
from app.services.asr_negative_controls import NEGATIVE_CONTROLS, create_negative_control  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    corpus = ROOT / "stress_corpus"; manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clean = manifest.get("cases") or []
    if len(clean) != 90:
        raise RuntimeError(f"Expected exactly 90 frozen clean cases, found {len(clean)}.")
    traffic = corpus / "noise" / "traffic.ogg"
    if not traffic.exists():
        raise RuntimeError("Missing verified real street-noise fixture: stress_corpus/noise/traffic.ogg")
    variants: list[dict] = []
    for case in sorted(clean, key=lambda item: item["id"]):
        source = corpus / case["path"]
        for scenario in STRESS_SCENARIOS:
            if scenario.name == "clean":
                continue
            rel = f"variants/{case['id']}--{scenario.name}.m4a"; target = corpus / rel
            if not target.exists() or target.stat().st_size < 1024:
                create_stress_variant(source, target, scenario.name, street_noise=traffic if scenario.requires_street_noise else None)
            variants.append({
                "id": f"{case['id']}--{scenario.name}", "parent_case_id": case["id"], "language": case["language"],
                "language_hint": case.get("language_hint", "auto"), "dataset": case.get("dataset"), "source": case.get("source"),
                "source_identifier": case.get("upstream_clip_id") or case.get("upstream_row_index") or case.get("source_utterance_ids"),
                "license": case.get("license"), "reference": case["reference"],
                "normalized_reference": case.get("normalized_reference") or (case.get("normalized_references") or {}).get("transcription_v1"),
                "scenario": scenario.name, "audio_path": rel, "duration": probe_duration(target), "audio_sha256": sha256(target),
                "stress_settings": {"version": "2026-08-13-v1", "ffmpeg": "deterministic", "noise_seed": 9001,
                    "street_noise_sha256": sha256(traffic) if scenario.name == "street_noise" else None},
            })
    controls: list[dict] = []
    for kind in NEGATIVE_CONTROLS:
        rel = f"negative_controls/{kind}.m4a"; target = corpus / rel
        if not target.exists() or target.stat().st_size < 1024:
            create_negative_control(target, kind, seconds=30.0)
        controls.append({"id": f"negative-{kind}", "language": "none", "source": "ClipKaro deterministic negative control",
            "license": "internal test fixture", "scenario": kind, "audio_path": rel, "duration": probe_duration(target),
            "audio_sha256": sha256(target), "reference": "", "normalized_reference": "", "settings": {"seconds": 30.0, "sample_rate": 16000}})
    manifest["schema_version"] = 3
    manifest["street_noise"] = "noise/traffic.ogg"
    manifest["stress_generation"] = {"version": "2026-08-13-v1", "scenarios": [s.name for s in STRESS_SCENARIOS if s.name != "clean"], "noise_seed": 9001}
    manifest["stress_cases"] = variants
    manifest["negative_controls"] = controls
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"clean": len(clean), "stress": len(variants), "negative_controls": len(controls)}, ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())

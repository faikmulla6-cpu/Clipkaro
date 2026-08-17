#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.asr_benchmark import probe_duration  # noqa: E402


SOURCES: dict[str, dict[str, Any]] = {
    "traffic": {
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Sunday_in_the_city_street_noise1.ogg",
        "source_page": "https://commons.wikimedia.org/wiki/File:Sunday_in_the_city_street_noise1.ogg",
        "license": "Public domain",
        "description": "Real city street/traffic ambience with cars, vans and mopeds.",
        "minimum_seconds": 60.0,
    },
    "cafe": {
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Cafe_ambiance.ogg",
        "source_page": "https://commons.wikimedia.org/wiki/File:Cafe_ambiance.ogg",
        "license": "CC0 1.0",
        "description": "Real café ambience with people chatting in the background.",
        "minimum_seconds": 60.0,
    },
    "fan": {
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Table_ventilator.ogg",
        "source_page": "https://commons.wikimedia.org/wiki/File:Table_ventilator.ogg",
        "license": "Public domain",
        "description": "Real table-fan/ventilator motor and airflow noise.",
        "minimum_seconds": 30.0,
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    with requests.get(
        url,
        stream=True,
        timeout=120,
        headers={"User-Agent": "ClipKaro-ASR-Qualification/1.0 (https://clipkaro.pro)"},
    ) as response:
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
                    total += len(chunk)
                    if total > 64 * 1024 * 1024:
                        raise RuntimeError(f"Noise fixture exceeded 64 MiB safety limit: {url}")
    if target.stat().st_size < 10_000:
        raise RuntimeError(f"Noise fixture was unexpectedly small: {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download reproducible real-world noise for ClipKaro ASR qualification.")
    parser.add_argument("--output-dir", default="stress_corpus/noise")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"schema_version": 1, "sources": {}}

    for name, source in SOURCES.items():
        target = output_dir / f"{name}.ogg"
        print(f"Downloading {name}: {source['description']}", flush=True)
        _download(str(source["download_url"]), target)
        duration = probe_duration(target)
        minimum = float(source["minimum_seconds"])
        if duration < minimum:
            raise RuntimeError(
                f"{name} fixture is only {duration:.1f}s; expected at least {minimum:.1f}s. "
                "Upstream media may have changed."
            )
        manifest["sources"][name] = {
            **source,
            "path": target.name,
            "bytes": target.stat().st_size,
            "duration_seconds": round(duration, 3),
            "sha256": _sha256(target),
        }
        print(f"  {duration:.1f}s sha256={manifest['sources'][name]['sha256']}", flush=True)

    manifest_path = output_dir / "noise-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote noise evidence to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.landscape_qualification import SOURCE_SPECS  # noqa: E402

LOCKED_SOURCE_FILENAMES = tuple(str(item["filename"]) for item in SOURCE_SPECS)


def _command(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"available": bool(path), "path": path}


def _version(command: list[str]) -> str | None:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        rows = (proc.stdout or proc.stderr).splitlines()
        return rows[0][:240] if rows else None
    except Exception:
        return None


def _visible_memory_mib() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def _free_disk_gib(path: Path) -> float:
    return round(shutil.disk_usage(path).free / (1024 ** 3), 2)


def _tcp_probe(host: str, port: int = 443, timeout: float = 3.0) -> dict[str, Any]:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            return {"reachable": False, "reason": "dns_no_addresses"}
        family, socktype, proto, _, sockaddr = addresses[0]
        with socket.socket(family, socktype, proto) as sock:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
        return {"reachable": True}
    except Exception as exc:
        return {"reachable": False, "reason": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record whether this host can execute ClipKaro's 30-export real landscape qualification."
    )
    parser.add_argument("--output", default="landscape-execution-preflight.json")
    parser.add_argument("--source-dir", default="")
    args = parser.parse_args()

    blockers: list[str] = []
    warnings: list[str] = []
    python_ok = sys.version_info[:2] == (3, 12)
    linux_x64 = platform.system() == "Linux" and platform.machine().lower() in {"x86_64", "amd64"}
    non_root = not hasattr(os, "geteuid") or os.geteuid() != 0
    memory_mib = _visible_memory_mib()
    disk_gib = _free_disk_gib(Path.cwd())

    if not linux_x64:
        blockers.append("qualification host must be Linux x64")
    if not python_ok:
        blockers.append(f"Python 3.12 required; found {sys.version_info.major}.{sys.version_info.minor}")
    if not non_root:
        blockers.append("qualification runner must use an unprivileged account")
    if memory_mib < 4096:
        blockers.append(f"at least 4 GiB visible RAM required; found {memory_mib} MiB")
    elif memory_mib < 7400:
        warnings.append(f"8 GB-class host recommended for repeatable 1080p export evidence; found {memory_mib} MiB")
    if disk_gib < 8:
        blockers.append(f"at least 8 GiB free disk required; found {disk_gib:.2f} GiB")
    elif disk_gib < 20:
        warnings.append(f"20+ GiB free disk recommended for source + 30 export artifacts; found {disk_gib:.2f} GiB")

    commands = {name: _command(name) for name in ("ffmpeg", "ffprobe", "git")}
    commands["gnu_time"] = {"available": Path("/usr/bin/time").is_file(), "path": "/usr/bin/time"}
    for name, info in commands.items():
        if not info["available"]:
            blockers.append(f"required command missing: {name}")

    modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("cv2", "requests")
    }
    missing_modules = [name for name, available in modules.items() if not available]
    if missing_modules:
        blockers.append("landscape QA Python modules missing: " + ", ".join(missing_modules))

    source_mode = "network"
    source_status: dict[str, Any]
    if args.source_dir:
        source_mode = "operator-supplied-real-media-cache"
        source_dir = Path(args.source_dir).expanduser().resolve()
        files = {
            name: {
                "exists": (source_dir / name).is_file(),
                "size_bytes": (source_dir / name).stat().st_size if (source_dir / name).is_file() else 0,
            }
            for name in LOCKED_SOURCE_FILENAMES
        }
        missing = [name for name, info in files.items() if not info["exists"] or info["size_bytes"] < 100_000]
        if missing:
            blockers.append("real landscape source cache is incomplete: " + ", ".join(missing))
        source_status = {"directory": str(source_dir), "files": files}
    else:
        network = _tcp_probe("commons.wikimedia.org")
        if not network["reachable"]:
            blockers.append("outbound HTTPS/DNS unavailable for Wikimedia real-media sources")
        source_status = {"commons.wikimedia.org": network}

    payload = {
        "schema_version": "clipkaro-landscape-execution-preflight-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "uid": os.geteuid() if hasattr(os, "geteuid") else None,
            "memory_mib": memory_mib,
            "free_disk_gib": disk_gib,
        },
        "commands": commands,
        "versions": {
            "ffmpeg": _version(["ffmpeg", "-version"]) if commands["ffmpeg"]["available"] else None,
            "ffprobe": _version(["ffprobe", "-version"]) if commands["ffprobe"]["available"] else None,
            "opencv": _version([sys.executable, "-c", "import cv2; print(cv2.__version__)"]) if modules["cv2"] else None,
        },
        "modules": modules,
        "source_mode": source_mode,
        "source_status": source_status,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ready": payload["ready"], "blockers": blockers, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

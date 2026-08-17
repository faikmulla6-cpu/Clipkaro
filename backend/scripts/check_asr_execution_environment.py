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


def _command(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"available": bool(path), "path": path}


def _visible_memory_mib() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def _free_disk_gib(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return round(usage.free / (1024 ** 3), 2)


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


def _version(command: list[str]) -> str | None:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        text = (proc.stdout or proc.stderr).splitlines()
        return text[0][:240] if text else None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Record whether this Linux host can execute ClipKaro's real ASR qualification.")
    parser.add_argument("--output", default="asr-execution-preflight.json")
    parser.add_argument("--check-runtime", action="store_true", help="Also require installed faster-whisper/WhisperX runtime modules.")
    args = parser.parse_args()

    blockers: list[str] = []
    warnings: list[str] = []
    memory_mib = _visible_memory_mib()
    disk_gib = _free_disk_gib(Path.cwd())
    python_ok = sys.version_info[:2] == (3, 12)
    non_root = not hasattr(os, "geteuid") or os.geteuid() != 0
    linux_x64 = platform.system() == "Linux" and platform.machine().lower() in {"x86_64", "amd64"}

    if not linux_x64:
        blockers.append("qualification host must be Linux x64")
    if not non_root:
        blockers.append("qualification runner must use an unprivileged account")
    if not python_ok:
        blockers.append(f"Python 3.12 required; found {sys.version_info.major}.{sys.version_info.minor}")
    if memory_mib < 7400:
        blockers.append(f"8 GB-class host required (>=7400 MiB visible RAM); found {memory_mib} MiB")
    elif memory_mib < 11264:
        warnings.append(f"12+ GiB is recommended for production-class WhisperX qualification; found {memory_mib} MiB")
    if disk_gib < 25:
        blockers.append(f"at least 25 GiB free disk required; found {disk_gib:.2f} GiB")
    elif disk_gib < 40:
        warnings.append(f"40+ GiB free disk recommended; found {disk_gib:.2f} GiB")

    commands = {name: _command(name) for name in ("ffmpeg", "ffprobe", "curl", "git")}
    commands["gnu_time"] = {"available": Path("/usr/bin/time").is_file(), "path": "/usr/bin/time"}
    for name, info in commands.items():
        if not info["available"]:
            blockers.append(f"required command missing: {name}")

    network_hosts = ("pypi.org", "huggingface.co", "openslr.org", "commons.wikimedia.org")
    network = {host: _tcp_probe(host) for host in network_hosts}
    unreachable = [host for host, result in network.items() if not result["reachable"]]
    if unreachable:
        blockers.append("outbound HTTPS/DNS unavailable for qualification sources: " + ", ".join(unreachable))

    runtime_modules: dict[str, bool] = {}
    if args.check_runtime:
        for name in ("faster_whisper", "whisperx", "torch", "torchaudio", "torchvision", "huggingface_hub"):
            runtime_modules[name] = importlib.util.find_spec(name) is not None
        missing = [name for name, available in runtime_modules.items() if not available]
        if missing:
            blockers.append("ASR/alignment runtime modules missing: " + ", ".join(missing))

    payload = {
        "schema_version": "clipkaro-asr-execution-preflight-v1",
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
        },
        "network": network,
        "runtime_modules": runtime_modules,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ready": payload["ready"], "blockers": blockers, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

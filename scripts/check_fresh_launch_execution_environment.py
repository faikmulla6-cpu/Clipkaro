#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]


def _command(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"available": bool(path), "path": path}


def _run(command: list[str], *, cwd: Path = ROOT, timeout: float = 8.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
        text = (proc.stdout or proc.stderr or "").strip().splitlines()
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "first_line": text[0][:300] if text else "",
        }
    except Exception as exc:
        return {"ok": False, "returncode": None, "reason": type(exc).__name__}


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


def _git_identity(tested_sha: str) -> dict[str, Any]:
    if not (ROOT / ".git").exists() or not shutil.which("git"):
        return {
            "available": False,
            "head": None,
            "tree": None,
            "tested_sha": tested_sha or None,
            "exact_sha_match": False,
            "clean": False,
            "reason": "exact Git checkout unavailable",
        }
    head = _run(["git", "rev-parse", "HEAD"])
    tree = _run(["git", "rev-parse", "HEAD^{tree}"])
    status = _run(["git", "status", "--porcelain"], timeout=15)
    head_sha = head.get("first_line") if head.get("ok") else None
    return {
        "available": bool(head.get("ok")),
        "head": head_sha,
        "tree": tree.get("first_line") if tree.get("ok") else None,
        "tested_sha": tested_sha or head_sha,
        "exact_sha_match": bool(head_sha and (tested_sha or head_sha) == head_sha),
        "clean": bool(status.get("ok") and not status.get("first_line")),
        "status_probe": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether this host can execute exact-SHA ClipKaro Fresh Launch QA.")
    parser.add_argument("--output", default="launch-qa/execution-preflight.json")
    parser.add_argument("--tested-sha", default=os.environ.get("TESTED_SHA", ""))
    args = parser.parse_args()

    blockers: list[str] = []
    warnings: list[str] = []
    commands = {name: _command(name) for name in ("git", "python3.12", "node", "npm", "ffmpeg", "ffprobe", "docker")}
    commands["gnu_time"] = {"available": Path("/usr/bin/time").is_file(), "path": "/usr/bin/time"}

    linux_x64 = platform.system() == "Linux" and platform.machine().lower() in {"x86_64", "amd64"}
    non_root = not hasattr(os, "geteuid") or os.geteuid() != 0
    memory_mib = _visible_memory_mib()
    disk_gib = _free_disk_gib(ROOT)

    if not linux_x64:
        blockers.append("Fresh Launch QA host must be Linux x64")
    if not non_root:
        blockers.append("launch QA runner must use an unprivileged account")
    for name in ("git", "python3.12", "node", "npm", "ffmpeg", "ffprobe", "docker"):
        if not commands[name]["available"]:
            blockers.append(f"required command missing: {name}")
    if not commands["gnu_time"]["available"]:
        blockers.append("required command missing: GNU /usr/bin/time")

    py312 = _run(["python3.12", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"]) if commands["python3.12"]["available"] else {"ok": False}
    if commands["python3.12"]["available"] and py312.get("first_line") != "3.12":
        blockers.append(f"Python 3.12 required; found {py312.get('first_line') or 'unknown'}")
    node = _run(["node", "-p", "process.versions.node.split('.')[0]"]) if commands["node"]["available"] else {"ok": False}
    if commands["node"]["available"] and node.get("first_line") != "20":
        blockers.append(f"Node.js 20 required; found major {node.get('first_line') or 'unknown'}")

    docker_info = _run(["docker", "info"], timeout=15) if commands["docker"]["available"] else {"ok": False}
    compose = _run(["docker", "compose", "version"]) if commands["docker"]["available"] else {"ok": False}
    if commands["docker"]["available"] and not docker_info.get("ok"):
        blockers.append("Docker daemon unavailable to the runner user")
    if commands["docker"]["available"] and not compose.get("ok"):
        blockers.append("Docker Compose v2 plugin unavailable")

    if memory_mib < 7400:
        blockers.append(f"8 GB-class host required (>=7400 MiB visible RAM); found {memory_mib} MiB")
    elif memory_mib < 11264:
        warnings.append(f"12+ GiB visible RAM recommended for worker image/WhisperX qualification; found {memory_mib} MiB")
    if disk_gib < 25:
        blockers.append(f"at least 25 GiB free disk required; found {disk_gib:.2f} GiB")
    elif disk_gib < 40:
        warnings.append(f"40+ GiB free disk recommended for Docker layers and dependency caches; found {disk_gib:.2f} GiB")

    git_identity = _git_identity(args.tested_sha.strip())
    if not git_identity["available"]:
        blockers.append("exact Git checkout is unavailable; an extracted ZIP cannot be release-certified")
    else:
        if not git_identity["exact_sha_match"]:
            blockers.append("checked-out Git SHA does not match TESTED_SHA")
        if not git_identity["clean"]:
            blockers.append("Git working tree is not clean before Fresh Launch QA")

    network_hosts = ("pypi.org", "files.pythonhosted.org", "download.pytorch.org", "registry.npmjs.org", "registry-1.docker.io")
    network = {host: _tcp_probe(host) for host in network_hosts}
    unreachable = [host for host, value in network.items() if not value["reachable"]]
    if unreachable:
        blockers.append("outbound HTTPS/DNS unavailable for required dependency/image resolution: " + ", ".join(unreachable))

    payload = {
        "schema_version": "clipkaro-fresh-launch-execution-preflight-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "candidate": git_identity,
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "uid": os.geteuid() if hasattr(os, "geteuid") else None,
            "python_running_checker": platform.python_version(),
            "memory_mib": memory_mib,
            "free_disk_gib": disk_gib,
        },
        "commands": commands,
        "versions": {
            "python3.12": py312.get("first_line"),
            "node_major": node.get("first_line"),
            "ffmpeg": _run(["ffmpeg", "-version"]).get("first_line") if commands["ffmpeg"]["available"] else None,
            "docker": _run(["docker", "--version"]).get("first_line") if commands["docker"]["available"] else None,
            "docker_compose": compose.get("first_line") if compose.get("ok") else None,
        },
        "network": network,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ready": payload["ready"], "blockers": blockers, "warnings": warnings}, indent=2))
    return 0 if payload["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

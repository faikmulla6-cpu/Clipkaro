from __future__ import annotations

import asyncio
import logging
import socket
import struct
from pathlib import Path

from app.core.config import get_settings


logger = logging.getLogger("clipkaro.security")


class UploadMalwareDetected(RuntimeError):
    def __init__(self, signature: str = "malware") -> None:
        super().__init__("The uploaded file failed the security scan.")
        self.signature = signature


class UploadScannerUnavailable(RuntimeError):
    pass


def _looks_like_supported_container(path: Path) -> bool:
    """Reject obvious extension spoofing before invoking any media parser.

    WebM/MKV use the EBML header. Modern MP4/MOV commonly expose an `ftyp`
    atom near the start; older QuickTime MOVs may legitimately begin with other
    ISO-BMFF atoms, so accept those and let FFprobe remain authoritative after
    malware scanning. Only the first 64 bytes are read into memory.
    """
    try:
        with path.open("rb") as source:
            head = source.read(64)
    except OSError:
        return False
    if len(head) < 8:
        return False
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return True
    if b"ftyp" in head:
        return True
    # Common valid QuickTime/ISO-BMFF first atoms. This avoids rejecting older
    # camera/phone MOV files before FFprobe can inspect them.
    return head[4:8] in {b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"}


def _clamd_scan(path: Path) -> str:
    settings = get_settings()
    host = settings.clamav_host.strip()
    if not host:
        raise UploadScannerUnavailable("ClamAV host is not configured.")

    timeout = max(2.0, float(settings.clamav_timeout_seconds))
    chunk_size = max(16, int(settings.clamav_chunk_kb)) * 1024
    try:
        with socket.create_connection((host, int(settings.clamav_port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            # INSTREAM avoids sharing the host filesystem with the scanner. The
            # upload crosses the private Docker network as length-prefixed bytes.
            sock.sendall(b"zINSTREAM\0")
            with path.open("rb") as source:
                while chunk := source.read(chunk_size):
                    sock.sendall(struct.pack("!I", len(chunk)))
                    sock.sendall(chunk)
            sock.sendall(struct.pack("!I", 0))
            response = bytearray()
            while len(response) < 8192:
                part = sock.recv(4096)
                if not part:
                    break
                response.extend(part)
                if b"\0" in part or b"\n" in part:
                    break
    except (OSError, TimeoutError, socket.timeout) as exc:
        raise UploadScannerUnavailable("The upload security scanner is unavailable.") from exc

    text = bytes(response).replace(b"\0", b"").decode("utf-8", errors="replace").strip()
    if text.endswith(" OK") or text == "stream: OK":
        return text
    if " FOUND" in text:
        signature = text.split(":", 1)[-1].rsplit(" FOUND", 1)[0].strip() or "malware"
        raise UploadMalwareDetected(signature)
    if "INSTREAM size limit exceeded" in text:
        raise UploadScannerUnavailable("The scanner stream limit is smaller than ClipKaro's upload limit.")
    raise UploadScannerUnavailable(f"ClamAV returned an unexpected response: {text[:240] or 'empty response'}")


def _clamd_ping(host: str, port: int, timeout: float) -> bool:
    """Use clamd's side-effect-free PING command; never expose its address."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"zPING\0")
            response = sock.recv(64).replace(b"\0", b"").strip().upper()
        return response == b"PONG"
    except (OSError, TimeoutError, socket.timeout):
        return False


async def probe_clamav_readiness() -> dict[str, object]:
    settings = get_settings()
    configured = bool(settings.clamav_host.strip())
    required = bool(settings.upload_scan_required)
    if not configured:
        return {
            "configured": False,
            "reachable": False,
            "required": required,
            "code": "unconfigured" if required else "disabled",
        }
    timeout = min(max(1.0, float(settings.preflight_network_timeout_seconds)),
                  max(2.0, float(settings.clamav_timeout_seconds)))
    reachable = await asyncio.to_thread(
        _clamd_ping, settings.clamav_host.strip(), int(settings.clamav_port), timeout
    )
    return {
        "configured": True,
        "reachable": reachable,
        "required": required,
        "code": "ready" if reachable else "unreachable",
    }


async def scan_upload(path: Path) -> dict[str, str]:
    settings = get_settings()

    # Existing unit/integration tests intentionally use tiny placeholder upload
    # bytes because they mock FFprobe/ASR later in the pipeline. Preserve that
    # sandbox behavior only when APP_ENV=test and malware scanning is disabled;
    # development/preview/production still pass through the signature boundary.
    if settings.app_env == "test" and not settings.upload_scan_required and not settings.clamav_host.strip():
        return {"status": "skipped", "engine": "clamav"}

    if not _looks_like_supported_container(path):
        raise UploadMalwareDetected("invalid-or-spoofed-video-container")

    if not settings.clamav_host.strip():
        if settings.upload_scan_required:
            raise UploadScannerUnavailable("Upload scanning is required but ClamAV is not configured.")
        return {"status": "skipped", "engine": "clamav"}

    try:
        result = await asyncio.to_thread(_clamd_scan, path)
        return {"status": "clean", "engine": "clamav", "detail": result}
    except UploadMalwareDetected:
        raise
    except UploadScannerUnavailable:
        if settings.upload_scan_required:
            raise
        logger.exception("Optional ClamAV scan unavailable for %s", path.name)
        return {"status": "unavailable", "engine": "clamav"}

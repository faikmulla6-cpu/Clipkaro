from __future__ import annotations

import asyncio
import hmac
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

VERSION = "1.0.0"
VIDEO_ID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
UPLOAD_SUFFIXES = tuple(
    item.strip().lower()
    for item in os.getenv(
        "INGESTION_UPLOAD_HOST_SUFFIXES",
        "backblazeb2.com,amazonaws.com,storage.googleapis.com",
    ).split(",")
    if item.strip()
)
MAX_CONCURRENCY = max(1, min(int(os.getenv("INGESTION_MAX_CONCURRENCY", "2")), 4))
POT_BASE_URL = os.getenv("POT_PROVIDER_BASE_URL", "http://127.0.0.1:4416").rstrip("/")
SHARED_SECRET = os.getenv("INGESTION_SHARED_SECRET", "")
ALLOW_HTTP_UPLOAD_FOR_TESTS = os.getenv("INGESTION_ALLOW_HTTP_UPLOAD_FOR_TESTS", "").strip().lower() in {"1", "true", "yes"}
REQUEST_TIMEOUT = max(60, min(int(os.getenv("INGESTION_REQUEST_TIMEOUT_SECONDS", "900")), 1800))
semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
app = FastAPI(title="ClipKaro YouTube Ingestion Worker", version=VERSION, docs_url=None, redoc_url=None)


class IngestRequest(BaseModel):
    url: str = Field(min_length=1, max_length=300)
    expected_video_id: str = Field(min_length=11, max_length=11)
    upload_url: str = Field(min_length=10, max_length=4000)
    max_minutes: float = Field(gt=0, le=1500)
    remaining_minutes: float = Field(gt=0, le=1500)
    max_bytes: int = Field(gt=0, le=536_870_912)


def _canonical_youtube_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.port:
        raise ValueError("invalid YouTube URL")
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        raise ValueError("invalid YouTube host")
    parts = [part for part in parsed.path.split("/") if part]
    video_id = ""
    if host == "youtu.be":
        video_id = parts[0] if parts else ""
    elif parsed.path.rstrip("/") == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif len(parts) >= 2 and parts[0].lower() in {"shorts", "embed", "live"}:
        video_id = parts[1]
    if len(video_id) != 11 or any(char not in VIDEO_ID_CHARS for char in video_id):
        raise ValueError("invalid YouTube video id")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def _upload_host_allowed(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.username or parsed.password or not host:
        return False
    if parsed.scheme == "https":
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in UPLOAD_SUFFIXES)
    return bool(ALLOW_HTTP_UPLOAD_FOR_TESTS and parsed.scheme == "http" and host in {"127.0.0.1", "localhost"})


def _auth_ok(authorization: str | None) -> bool:
    if len(SHARED_SECRET) < 32 or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization[7:], SHARED_SECRET)
def _yt_dlp_base_args() -> list[str]:
    return [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=mweb",
        "--extractor-args", f"youtubepot-bgutilhttp:base_url={POT_BASE_URL}",
        "--socket-timeout", "20",
        "--retries", "2",
        "--fragment-retries", "2",
    ]


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _safe_title(value: object) -> str:
    title = " ".join(str(value or "YouTube video").split())[:120]
    return title or "YouTube video"
def _ingest(body: IngestRequest) -> dict[str, object]:
    canonical, video_id = _canonical_youtube_url(body.url)
    if video_id != body.expected_video_id:
        raise HTTPException(422, "YouTube video id did not match the authorized job.")
    if not _upload_host_allowed(body.upload_url):
        raise HTTPException(422, "Upload destination is not an approved ClipKaro storage host.")

    info_cmd = _yt_dlp_base_args() + ["--skip-download", "--dump-single-json", canonical]
    info_result = _run(info_cmd, timeout=min(120, REQUEST_TIMEOUT))
    if info_result.returncode != 0:
        raise HTTPException(502, "YouTube did not allow this ingestion request.")
    try:
        info = json.loads(info_result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "YouTube metadata could not be read safely.") from exc

    if str(info.get("id") or "") != video_id or info.get("entries"):
        raise HTTPException(422, "Only one direct YouTube video can be imported.")
    if bool(info.get("is_live")) or str(info.get("live_status") or "") == "is_live":
        raise HTTPException(422, "Live broadcasts can be imported after the stream finishes.")
    duration = float(info.get("duration") or 0)
    allowed_minutes = min(float(body.max_minutes), float(body.remaining_minutes))
    if duration <= 0 or duration / 60.0 > allowed_minutes + 1e-6:
        raise HTTPException(422, "This video is longer than the creator's available Karo Minutes.")
    with tempfile.TemporaryDirectory(prefix="clipkaro-ingest-") as temp_dir:
        output_template = str(Path(temp_dir) / "source.%(ext)s")
        download_cmd = _yt_dlp_base_args() + [
            "-f", "bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]",
            "--merge-output-format", "mp4",
            "--max-filesize", str(body.max_bytes),
            "--concurrent-fragments", "1",
            "--restrict-filenames",
            "--no-overwrites",
            "-o", output_template,
            canonical,
        ]
        result = _run(download_cmd, timeout=REQUEST_TIMEOUT)
        if result.returncode != 0:
            raise HTTPException(502, "YouTube media download did not complete.")
        candidates = [path for path in Path(temp_dir).iterdir() if path.is_file() and path.suffix.lower() == ".mp4"]
        if not candidates:
            raise HTTPException(502, "YouTube did not produce a usable MP4 source.")
        source = max(candidates, key=lambda path: path.stat().st_size)
        size = source.stat().st_size
        if size <= 0 or size > body.max_bytes:
            raise HTTPException(413, "Downloaded source exceeded ClipKaro's source-size limit.")

        try:
            with source.open("rb") as handle:
                response = requests.put(
                    body.upload_url,
                    data=handle,
                    headers={"Content-Type": "video/mp4"},
                    timeout=(10, 180),
                    allow_redirects=False,
                )
        except requests.RequestException as exc:
            raise HTTPException(502, "Private storage upload could not be reached.") from exc
        if response.status_code not in {200, 201, 204}:
            raise HTTPException(502, "Private storage rejected the ingested source.")

    return {
        "video_id": video_id,
        "title": _safe_title(info.get("title")),
        "duration": duration,
        "size": size,
        "content_type": "video/mp4",
        "worker_version": VERSION,
    }


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "version": VERSION,
        "pot_provider": POT_BASE_URL,
        "max_concurrency": MAX_CONCURRENCY,
    }


@app.post("/v1/ingest/youtube")
async def ingest_youtube(body: IngestRequest, authorization: str | None = Header(default=None)) -> dict[str, object]:
    if not _auth_ok(authorization):
        raise HTTPException(401, "Unauthorized")
    async with semaphore:
        return await asyncio.to_thread(_ingest, body)

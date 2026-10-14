from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PROVIDER_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{6,128}$")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
_DEFAULT_PROVIDER_DOWNLOAD_SUFFIXES = ("socialkit.dev", "amazonaws.com", "cloudfront.net")


class YouTubeImportError(RuntimeError):
    """A bounded, creator-safe failure that may be shown without provider details."""

    def __init__(self, public_message: str, *, retry_with_provider: bool = False) -> None:
        super().__init__("YOUTUBE_IMPORT_FAILED")
        self.public_message = public_message
        self.retry_with_provider = retry_with_provider


@dataclass(frozen=True)
class YouTubeSource:
    path: Path
    video_id: str
    title: str
    duration: float


def canonicalize_youtube_url(value: str) -> tuple[str, str]:
    """Return a canonical watch URL and video id without accepting arbitrary hosts."""
    raw = str(value or "").strip()
    if not raw or len(raw) > 500:
        raise ValueError("Paste a valid YouTube video link.")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("Paste a valid YouTube video link.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"https", "http"} or host not in _YOUTUBE_HOSTS:
        raise ValueError("Only YouTube video links are supported.")
    if parsed.username or parsed.password or parsed.port is not None:
        raise ValueError("This YouTube link contains unsupported connection details.")

    video_id = ""
    parts = [part for part in parsed.path.split("/") if part]
    if host == "youtu.be":
        video_id = parts[0] if parts else ""
    elif parsed.path.rstrip("/") == "/watch":
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    elif len(parts) >= 2 and parts[0].lower() in {"shorts", "embed", "live"}:
        video_id = parts[1]

    if not _VIDEO_ID.fullmatch(video_id):
        raise ValueError("Paste a direct YouTube video, Shorts, or live-replay link.")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def _safe_title(value: object) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    return title[:120] or "YouTube video"


def _validate_duration(duration: float, max_minutes: float, remaining_minutes: float) -> None:
    if duration <= 0:
        raise YouTubeImportError("ClipKaro could not verify this video's duration. Try another video.")
    source_minutes = duration / 60.0
    if source_minutes > float(max_minutes) + 1e-6:
        raise YouTubeImportError(
            f"Your plan supports a single source video up to {max_minutes:g} minutes. Choose a shorter video."
        )
    if source_minutes > float(remaining_minutes) + 1e-6:
        raise YouTubeImportError(
            f"You have {remaining_minutes:g} Karo Minutes left, but this video needs {source_minutes:.1f}."
        )


def _read_failure_message(exc: Exception) -> str:
    detail = str(exc).lower()
    if "sign in to confirm" in detail or "not a bot" in detail:
        return (
            "YouTube blocked the secure server import before download. "
            "Your Karo Minutes were not charged. Upload your original file instead."
        )
    return "ClipKaro could not read this YouTube video. Make sure the video is available and try again."


def _provider_host_suffixes(value: str) -> tuple[str, ...]:
    items = tuple(part.strip().lower().lstrip(".") for part in str(value or "").split(",") if part.strip())
    return items or _DEFAULT_PROVIDER_DOWNLOAD_SUFFIXES


def _validate_provider_download_url(value: str, allowed_suffixes: tuple[str, ...]) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError as exc:
        raise YouTubeImportError("The YouTube import provider returned an invalid media URL.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise YouTubeImportError("The YouTube import provider returned an invalid media URL.")
    if not any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes):
        raise YouTubeImportError("The YouTube import provider returned an untrusted media host.")
    return parsed.geturl()


def _provider_failure(message: str) -> YouTubeImportError:
    return YouTubeImportError(
        message or "ClipKaro could not import this YouTube video automatically. No Karo Minutes were charged."
    )


def _download_provider_file(
    session: requests.Session,
    url: str,
    target: Path,
    *,
    max_bytes: int,
    timeout_seconds: float,
    allowed_suffixes: tuple[str, ...],
) -> None:
    current = _validate_provider_download_url(url, allowed_suffixes)
    response = None
    try:
        for _ in range(4):
            response = session.get(
                current,
                stream=True,
                allow_redirects=False,
                timeout=(10.0, max(20.0, float(timeout_seconds))),
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = str(response.headers.get("Location") or "").strip()
                response.close()
                if not location:
                    raise _provider_failure("The YouTube import provider returned an incomplete download redirect.")
                current = _validate_provider_download_url(urljoin(current, location), allowed_suffixes)
                response = None
                continue
            response.raise_for_status()
            try:
                declared = int(response.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                declared = 0
            if declared > int(max_bytes):
                raise YouTubeImportError("This video is above ClipKaro's 500 MB source limit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > int(max_bytes):
                        raise YouTubeImportError("This video is above ClipKaro's 500 MB source limit.")
                    handle.write(chunk)
            if written <= 0:
                raise _provider_failure("The YouTube import provider returned an empty media file.")
            return
        raise _provider_failure("The YouTube import provider returned too many download redirects.")
    except YouTubeImportError:
        target.unlink(missing_ok=True)
        raise
    except requests.RequestException as exc:
        target.unlink(missing_ok=True)
        raise _provider_failure("ClipKaro could not fetch the imported YouTube media. No Karo Minutes were charged.") from exc
    finally:
        if response is not None:
            response.close()


def _download_socialkit_source(
    canonical: str,
    expected_id: str,
    destination: Path,
    *,
    access_key: str,
    api_base_url: str,
    quality: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
    download_timeout_seconds: float,
    download_host_suffixes: str,
    max_minutes: float,
    remaining_minutes: float,
    max_bytes: int,
) -> YouTubeSource:
    key = str(access_key or "").strip()
    if not key:
        raise _provider_failure("YouTube link importing is temporarily unavailable. No Karo Minutes were charged.")
    allowed_minutes = min(float(max_minutes), float(remaining_minutes))
    if allowed_minutes <= 0:
        raise YouTubeImportError("You do not have enough Karo Minutes to process another video.")
    max_duration = max(1, int(math.floor(allowed_minutes * 60.0 + 1e-6)))
    base = str(api_base_url or "https://api.socialkit.dev").strip().rstrip("/")
    parsed_base = urlsplit(base)
    base_host = (parsed_base.hostname or "").lower().rstrip(".")
    if (
        parsed_base.scheme != "https"
        or base_host != "api.socialkit.dev"
        or parsed_base.username
        or parsed_base.password
        or parsed_base.port not in {None, 443}
    ):
        raise _provider_failure("YouTube link importing is temporarily unavailable. No Karo Minutes were charged.")

    session = requests.Session()
    headers = {"x-access-key": key, "Accept": "application/json"}
    try:
        started = session.post(
            f"{base}/v2/youtube/download",
            headers={**headers, "Content-Type": "application/json"},
            json={"url": canonical, "quality": str(quality or "480p"), "format": "mp4", "max_duration": max_duration},
            timeout=(10.0, 30.0),
        )
        started.raise_for_status()
        payload = started.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        job_id = str((data or {}).get("jobId") or "")
        if not bool(payload.get("success")) or not _PROVIDER_JOB_ID.fullmatch(job_id):
            raise _provider_failure("ClipKaro's YouTube import provider could not start this video. No Karo Minutes were charged.")

        deadline = time.monotonic() + max(30.0, float(timeout_seconds))
        ready: dict | None = None
        while time.monotonic() < deadline:
            status_response = session.get(
                f"{base}/v2/downloads/{job_id}",
                headers=headers,
                timeout=(10.0, 30.0),
            )
            status_response.raise_for_status()
            status_payload = status_response.json()
            status_data = status_payload.get("data") if isinstance(status_payload, dict) else None
            status = str((status_data or {}).get("status") or "").lower()
            if status == "ready":
                ready = status_data
                break
            if status == "failed":
                raise _provider_failure("ClipKaro could not import this YouTube video automatically. No Karo Minutes were charged.")
            if status not in {"queued", "processing"}:
                raise _provider_failure("ClipKaro received an invalid response while importing this YouTube video.")
            time.sleep(max(0.25, float(poll_interval_seconds)))
        if ready is None:
            raise _provider_failure("YouTube import took too long. No Karo Minutes were charged; please retry.")

        duration = float(ready.get("durationSeconds") or 0)
        _validate_duration(duration, max_minutes, remaining_minutes)
        size_mb = float(str(ready.get("fileSizeMB") or "0").replace("MB", "").strip() or 0)
        if size_mb > 0 and size_mb * 1024 * 1024 > int(max_bytes):
            raise YouTubeImportError("This video is above ClipKaro's 500 MB source limit.")
        download_url = str(ready.get("downloadUrl") or "")
        target = destination / "source.mp4"
        _download_provider_file(
            session,
            download_url,
            target,
            max_bytes=max_bytes,
            timeout_seconds=download_timeout_seconds,
            allowed_suffixes=_provider_host_suffixes(download_host_suffixes),
        )
        return YouTubeSource(
            path=target,
            video_id=expected_id,
            title=_safe_title(ready.get("title")),
            duration=duration,
        )
    except YouTubeImportError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise _provider_failure("ClipKaro's YouTube import provider is temporarily unavailable. No Karo Minutes were charged.") from exc
    finally:
        session.close()


def _download_native_source(
    canonical: str,
    expected_id: str,
    destination: Path,
    *,
    max_minutes: float,
    remaining_minutes: float,
    max_bytes: int,
) -> YouTubeSource:
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - deployment contract catches this
        raise YouTubeImportError(
            "YouTube importing is temporarily unavailable. Please try again shortly.",
            retry_with_provider=True,
        ) from exc

    common = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(common) as inspector:
            info = inspector.extract_info(canonical, download=False)
    except Exception as exc:
        raise YouTubeImportError(_read_failure_message(exc), retry_with_provider=True) from exc

    if not isinstance(info, dict) or str(info.get("id") or "") != expected_id or info.get("entries"):
        raise YouTubeImportError("Paste a direct link to one YouTube video, not a playlist.")
    if bool(info.get("is_live")):
        raise YouTubeImportError("Live broadcasts can be imported after the stream has finished.")
    duration = float(info.get("duration") or 0)
    _validate_duration(duration, max_minutes, remaining_minutes)

    def enforce_size(progress: dict) -> None:
        downloaded = int(progress.get("downloaded_bytes") or 0)
        if downloaded > max_bytes:
            raise YouTubeImportError("This video is above ClipKaro's 500 MB source limit.")

    options = {
        **common,
        "outtmpl": str(destination / "source.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]",
        "merge_output_format": "mp4",
        "max_filesize": max_bytes,
        "concurrent_fragment_downloads": 1,
        "progress_hooks": [enforce_size],
        "overwrites": False,
        "restrictfilenames": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.extract_info(canonical, download=True)
    except YouTubeImportError:
        raise
    except Exception as exc:
        raise YouTubeImportError(
            "ClipKaro could not import this YouTube video. No Karo Minutes were charged.",
            retry_with_provider=True,
        ) from exc

    root = destination.resolve()
    candidates = [
        item for item in destination.iterdir()
        if item.is_file() and item.suffix.lower() in _VIDEO_EXTENSIONS and root in item.resolve().parents
    ]
    if not candidates:
        raise YouTubeImportError(
            "The YouTube video did not produce a usable media file. No Karo Minutes were charged.",
            retry_with_provider=True,
        )
    source = max(candidates, key=lambda item: item.stat().st_size)
    size = source.stat().st_size
    if size <= 0 or size > max_bytes:
        raise YouTubeImportError("This video is above ClipKaro's 500 MB source limit.")
    return YouTubeSource(
        path=source,
        video_id=expected_id,
        title=_safe_title(info.get("title")),
        duration=duration,
    )


def download_youtube_source(
    url: str,
    destination: Path,
    *,
    max_minutes: float,
    remaining_minutes: float,
    max_bytes: int,
    ingestion_provider: str = "native",
    socialkit_access_key: str = "",
    socialkit_api_base_url: str = "https://api.socialkit.dev",
    socialkit_quality: str = "480p",
    socialkit_poll_interval_seconds: float = 3.0,
    socialkit_timeout_seconds: float = 600.0,
    socialkit_download_timeout_seconds: float = 120.0,
    socialkit_download_host_suffixes: str = "socialkit.dev,amazonaws.com,cloudfront.net",
) -> YouTubeSource:
    """Download one bounded YouTube source, with an optional provider fallback."""
    canonical, expected_id = canonicalize_youtube_url(url)
    destination.mkdir(parents=True, exist_ok=True)
    provider = str(ingestion_provider or "native").strip().lower()
    if provider not in {"native", "auto", "socialkit"}:
        raise YouTubeImportError("YouTube importing is temporarily unavailable. No Karo Minutes were charged.")

    provider_kwargs = dict(
        access_key=socialkit_access_key,
        api_base_url=socialkit_api_base_url,
        quality=socialkit_quality,
        poll_interval_seconds=socialkit_poll_interval_seconds,
        timeout_seconds=socialkit_timeout_seconds,
        download_timeout_seconds=socialkit_download_timeout_seconds,
        download_host_suffixes=socialkit_download_host_suffixes,
        max_minutes=max_minutes,
        remaining_minutes=remaining_minutes,
        max_bytes=max_bytes,
    )
    if provider == "socialkit":
        return _download_socialkit_source(canonical, expected_id, destination, **provider_kwargs)

    try:
        return _download_native_source(
            canonical,
            expected_id,
            destination,
            max_minutes=max_minutes,
            remaining_minutes=remaining_minutes,
            max_bytes=max_bytes,
        )
    except YouTubeImportError as native_error:
        if provider != "auto" or not native_error.retry_with_provider or not str(socialkit_access_key or "").strip():
            raise
        for item in destination.glob("source.*"):
            item.unlink(missing_ok=True)
        return _download_socialkit_source(canonical, expected_id, destination, **provider_kwargs)

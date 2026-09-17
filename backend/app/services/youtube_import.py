from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


class YouTubeImportError(RuntimeError):
    """A bounded, creator-safe failure that may be shown without provider details."""

    def __init__(self, public_message: str) -> None:
        super().__init__("YOUTUBE_IMPORT_FAILED")
        self.public_message = public_message


@dataclass(frozen=True)
class YouTubeSource:
    path: Path
    video_id: str
    title: str
    duration: float


def canonicalize_youtube_url(value: str) -> tuple[str, str]:
    """Return a canonical watch URL and video id without accepting arbitrary hosts.

    The worker only ever receives a URL rebuilt from the validated eleven-character
    video id. User-controlled hosts, ports, credentials, fragments and paths are
    therefore never forwarded to the remote importer.
    """
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


def _read_failure_message(exc: Exception) -> str:
    detail = str(exc).lower()
    if "sign in to confirm" in detail or "not a bot" in detail:
        return (
            "YouTube blocked the secure server import before download. "
            "Your Karo Minutes were not charged. Upload your original file instead."
        )
    return "ClipKaro could not read this YouTube video. Make sure the video is available and try again."


def download_youtube_source(
    url: str,
    destination: Path,
    *,
    max_minutes: float,
    remaining_minutes: float,
    max_bytes: int,
) -> YouTubeSource:
    """Inspect then download exactly one bounded YouTube video into scratch space.

    yt-dlp is imported lazily so the internet-facing API remains independent of
    the downloader. Production installs yt-dlp only as a server-side dependency;
    no cookies, browser profile or user-supplied downloader options are accepted.
    """
    canonical, expected_id = canonicalize_youtube_url(url)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - deployment contract catches this
        raise YouTubeImportError("YouTube importing is temporarily unavailable. Please try again shortly.") from exc

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
        raise YouTubeImportError(_read_failure_message(exc)) from exc

    if not isinstance(info, dict) or str(info.get("id") or "") != expected_id or info.get("entries"):
        raise YouTubeImportError("Paste a direct link to one YouTube video, not a playlist.")
    if bool(info.get("is_live")):
        raise YouTubeImportError("Live broadcasts can be imported after the stream has finished.")
    duration = float(info.get("duration") or 0)
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
            "ClipKaro could not import this YouTube video. Make sure it is available and try again."
        ) from exc

    root = destination.resolve()
    candidates = [
        item for item in destination.iterdir()
        if item.is_file() and item.suffix.lower() in _VIDEO_EXTENSIONS
        and root in item.resolve().parents
    ]
    if not candidates:
        raise YouTubeImportError("The YouTube video did not produce a usable media file. Try another video.")
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

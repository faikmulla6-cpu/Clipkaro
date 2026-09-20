from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.database import execute, fetch_all, fetch_one
from app.services.jobs import update_job, utcnow
from app.services.storage import get_storage_provider, validate_object_key
from app.services.storage_paths import confined_export_path

logger = logging.getLogger("clipkaro.post_karo")

ZERNIO_API_ROOT = "https://zernio.com/api"
SUPPORTED_POST_KARO_PLATFORMS = {"instagram", "youtube"}
_API_KEY_PATTERN = re.compile(r"^sk_[0-9A-Fa-f]{64}$")
_SECRET_PATTERN = re.compile(r"sk_[0-9A-Za-z_-]{20,}")


class PostKaroProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.public_message = message
        self.status_code = status_code


def _cipher() -> Fernet:
    settings = get_settings()
    secret = settings.post_karo_encryption_key.strip()
    if not secret:
        if settings.app_env.strip().lower() == "production":
            raise PostKaroProviderError(
                "Post Karo secure storage is temporarily unavailable. Please try again later.",
                status_code=503,
            )
        # Local/test compatibility only. Production always requires a dedicated
        # key so JWT/session signing and provider-credential encryption are split.
        secret = settings.secret_key
    material = hashlib.sha256(("clipkaro:post-karo:v1:" + secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_api_key(api_key: str) -> str:
    return "v1:" + _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str:
    value = str(ciphertext or "")
    if not value.startswith("v1:"):
        raise PostKaroProviderError("Post Karo needs to be reconnected securely.", status_code=409)
    try:
        return _cipher().decrypt(value[3:].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise PostKaroProviderError("Post Karo needs to be reconnected securely.", status_code=409) from exc


def validate_api_key_shape(api_key: str) -> str:
    value = str(api_key or "").strip()
    if not _API_KEY_PATTERN.fullmatch(value):
        raise ValueError("Paste a valid Zernio API key.")
    return value


def mask_api_key(api_key: str) -> str:
    value = str(api_key)
    return f"{value[:7]}••••••••{value[-4:]}"


def fingerprint_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:20]


def _safe_provider_text(value: Any, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = _SECRET_PATTERN.sub("sk_••••••••", text)
    return (text[:360] or fallback).strip()


def _provider_message(response: httpx.Response) -> str:
    # Never expose provider response bodies directly to creators. They may
    # contain account ids, upstream diagnostics or other integration metadata.
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = {}
    code = str(payload.get("code") or "").strip().upper() if isinstance(payload, dict) else ""
    if response.status_code == 401:
        return "Your Post Karo connection is no longer valid. Reconnect it and try again."
    if response.status_code == 403:
        if "DISCONNECT" in code or "CONNECTION" in code or "PERMISSION" in code:
            return "This social account needs permission again. Reconnect it in Post Karo and retry."
        return "Post Karo does not have permission to complete this action. Reconnect and try again."
    if response.status_code == 409:
        if "DISCONNECT" in code or "CONNECTION" in code:
            return "One selected social account needs to be reconnected before publishing."
        return "This publishing request conflicts with an existing post. Refresh Post Karo and try again."
    if response.status_code == 429:
        return "This social account is temporarily rate-limited. Try again a little later."
    if response.status_code in {502, 503, 504}:
        return "The publishing service is temporarily unavailable. Your ClipKaro Short is still safe."
    if response.status_code == 400:
        return "The publishing service could not accept this post. Review the title, caption and selected accounts."
    return "The publishing service could not complete this request. Your ClipKaro Short is still safe."


class ZernioClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = validate_api_key_shape(api_key)
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if request_id:
            headers["x-request-id"] = request_id
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.request(
                    method,
                    ZERNIO_API_ROOT + path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise PostKaroProviderError(
                "The publishing service is temporarily unreachable. Your post was not duplicated; retry safely."
            ) from exc
        if response.status_code >= 400:
            raise PostKaroProviderError(_provider_message(response), status_code=response.status_code)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise PostKaroProviderError("The publishing service returned an unreadable response.") from exc
        return response.status_code, payload if isinstance(payload, dict) else {}

    async def validate(self) -> None:
        # Zernio provides a credential-verification endpoint specifically for
        # this purpose, so validation does not need to read any user resources.
        await self._request("GET", "/v1/auth/verify")

    async def ensure_clipkaro_profile(self, profile_name: str) -> str:
        safe_name = str(profile_name or "").strip()
        if not safe_name.startswith("ClipKaro-") or len(safe_name) > 64:
            raise ValueError("Invalid ClipKaro publishing profile name.")
        _, payload = await self._request("GET", "/v1/profiles")
        profiles = payload.get("profiles") or payload.get("data") or []
        if isinstance(profiles, list):
            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                if str(profile.get("name") or "").strip().casefold() == safe_name.casefold():
                    profile_id = str(profile.get("_id") or profile.get("id") or "").strip()
                    if profile_id:
                        return profile_id
        _, created = await self._request(
            "POST",
            "/v1/profiles",
            # Each ClipKaro user gets a separate pseudonymous Zernio profile,
            # even if two ClipKaro accounts intentionally reuse one Zernio team key.
            json_body={"name": safe_name},
        )
        profile = created.get("profile") or {}
        profile_id = str(profile.get("_id") or profile.get("id") or "").strip()
        if not profile_id:
            raise PostKaroProviderError("Zernio connected, but ClipKaro could not create its publishing profile.")
        return profile_id

    async def connect_url(self, platform: str, profile_id: str, redirect_url: str) -> str:
        if platform not in SUPPORTED_POST_KARO_PLATFORMS:
            raise ValueError("Unsupported Post Karo platform.")
        params: dict[str, Any] = {"profileId": profile_id, "redirect_url": redirect_url}
        if platform == "instagram":
            params["loginMethod"] = "instagram_login"
        _, payload = await self._request("GET", f"/v1/connect/{platform}", params=params)
        url = str(payload.get("authUrl") or "").strip()
        if not url.startswith("https://"):
            raise PostKaroProviderError("The social sign-in link could not be created.")
        return url

    async def list_accounts(self, profile_id: str) -> list[dict[str, Any]]:
        _, payload = await self._request(
            "GET", "/v1/accounts", params={"profileId": profile_id, "limit": 100}
        )
        accounts = payload.get("accounts") or payload.get("data") or []
        return [item for item in accounts if isinstance(item, dict)] if isinstance(accounts, list) else []

    async def account_health(self, profile_id: str) -> list[dict[str, Any]]:
        try:
            _, payload = await self._request(
                "GET", "/v1/accounts/health", params={"profileId": profile_id}
            )
        except PostKaroProviderError:
            return []
        items = payload.get("accounts") or payload.get("data") or payload.get("health") or []
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    async def upload_media(self, source: Path) -> str:
        size = source.stat().st_size
        _, presign = await self._request(
            "POST",
            "/v1/media/presign",
            json_body={"filename": source.name, "contentType": "video/mp4", "size": size},
        )
        upload_url = str(presign.get("uploadUrl") or presign.get("upload_url") or "").strip()
        public_url = str(
            presign.get("publicUrl") or presign.get("public_url")
            or presign.get("url") or presign.get("downloadUrl") or ""
        ).strip()
        if not upload_url.startswith("https://") or not public_url.startswith("https://"):
            raise PostKaroProviderError("The publishing service could not prepare the Short upload.")

        async def chunks():
            with source.open("rb") as handle:
                while True:
                    block = await asyncio.to_thread(handle.read, 1024 * 1024)
                    if not block:
                        break
                    yield block

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=20.0)) as client:
                response = await client.put(
                    upload_url,
                    headers={"Content-Type": "video/mp4"},
                    content=chunks(),
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise PostKaroProviderError("The Short upload was interrupted. Retry Post Karo safely.") from exc
        if response.status_code >= 400:
            raise PostKaroProviderError("The publishing service could not receive this Short.")
        return public_url

    async def create_post(
        self, payload: dict[str, Any], *, request_id: str
    ) -> tuple[int, dict[str, Any]]:
        return await self._request(
            "POST", "/v1/posts", json_body=payload, request_id=request_id
        )

    async def get_post(self, post_id: str) -> dict[str, Any]:
        _, payload = await self._request("GET", f"/v1/posts/{post_id}")
        return payload


def _provider_account_id(item: dict[str, Any]) -> str:
    return str(item.get("_id") or item.get("id") or item.get("accountId") or "").strip()


def _health_account_id(item: dict[str, Any]) -> str:
    account = item.get("account")
    if isinstance(account, dict):
        return str(account.get("_id") or account.get("id") or account.get("accountId") or "").strip()
    return str(item.get("accountId") or item.get("_id") or item.get("id") or "").strip()


def _can_post(item: dict[str, Any]) -> bool:
    value = item.get("canPost")
    if value is None and isinstance(item.get("capabilities"), dict):
        value = item["capabilities"].get("canPost")
    return value is not False


async def sync_supported_accounts(user_id: str, api_key: str, profile_id: str) -> list[dict[str, Any]]:
    client = ZernioClient(api_key)
    accounts, health = await asyncio.gather(
        client.list_accounts(profile_id),
        client.account_health(profile_id),
    )
    health_by_id = {_health_account_id(item): item for item in health if _health_account_id(item)}
    timestamp = utcnow()
    seen: set[str] = set()
    for item in accounts:
        platform = str(item.get("platform") or "").strip().lower()
        account_id = _provider_account_id(item)
        if platform not in SUPPORTED_POST_KARO_PLATFORMS or not account_id:
            continue
        profile_value = str(
            item.get("profileId")
            or ((item.get("profile") or {}).get("_id") if isinstance(item.get("profile"), dict) else "")
            or ""
        ).strip()
        if profile_value and profile_value != profile_id:
            continue
        seen.add(platform)
        health_item = health_by_id.get(account_id, {})
        username = str(item.get("username") or item.get("handle") or "").strip()[:180]
        display_name = str(item.get("displayName") or item.get("name") or username).strip()[:180]
        active = item.get("isActive") is not False
        can_post = active and _can_post(health_item)
        status = "connected" if active and can_post else "attention"
        existing = await fetch_one(
            "SELECT id,created_at FROM post_karo_accounts WHERE user_id=? AND platform=?",
            (user_id, platform),
        )
        row_id = str((existing or {}).get("id") or uuid.uuid4())
        created_at = str((existing or {}).get("created_at") or timestamp)
        await execute(
            """INSERT INTO post_karo_accounts(
                 id,user_id,platform,provider_account_id,username,display_name,can_post,
                 connection_status,health_json,last_synced_at,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id,platform) DO UPDATE SET
                 provider_account_id=excluded.provider_account_id,username=excluded.username,
                 display_name=excluded.display_name,can_post=excluded.can_post,
                 connection_status=excluded.connection_status,health_json=excluded.health_json,
                 last_synced_at=excluded.last_synced_at,updated_at=excluded.updated_at""",
            (
                row_id, user_id, platform, account_id, username, display_name, int(can_post),
                status, json.dumps(health_item, separators=(",", ":"), ensure_ascii=False),
                timestamp, created_at, timestamp,
            ),
        )
    cached = await fetch_all(
        "SELECT platform FROM post_karo_accounts WHERE user_id=?", (user_id,)
    )
    for row in cached:
        platform = str(row.get("platform") or "")
        if platform not in seen:
            await execute(
                "UPDATE post_karo_accounts SET can_post=0,connection_status='disconnected',updated_at=? "
                "WHERE user_id=? AND platform=?",
                (timestamp, user_id, platform),
            )
    return await fetch_all(
        "SELECT * FROM post_karo_accounts WHERE user_id=? ORDER BY platform", (user_id,)
    )


def _snapshot_platforms(snapshot: dict[str, Any], accounts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    if snapshot.get("instagram_enabled"):
        account = accounts.get("instagram")
        if not account or not account.get("can_post"):
            raise PostKaroProviderError("Instagram needs to be connected again before this Short can post.", status_code=409)
        caption = str(snapshot.get("instagram_caption") or "").strip()
        hashtags = [str(x).strip() for x in snapshot.get("instagram_hashtags") or [] if str(x).strip()]
        instagram_text = "\n\n".join(part for part in (caption, " ".join(hashtags)) if part)
        targets.append({
            "platform": "instagram",
            "accountId": account["provider_account_id"],
            "customContent": instagram_text,
            "platformSpecificData": {"shareToFeed": True},
        })
    if snapshot.get("youtube_enabled"):
        account = accounts.get("youtube")
        if not account or not account.get("can_post"):
            raise PostKaroProviderError("YouTube needs to be connected again before this Short can post.", status_code=409)
        targets.append({
            "platform": "youtube",
            "accountId": account["provider_account_id"],
            "customContent": str(snapshot.get("youtube_description") or "").strip(),
            "platformSpecificData": {
                "title": str(snapshot.get("youtube_title") or "").strip(),
                "visibility": str(snapshot.get("youtube_visibility") or "public"),
            },
        })
    if not targets:
        raise PostKaroProviderError("Choose Instagram, YouTube, or both before posting.", status_code=409)
    return targets


def build_post_payload(
    snapshot: dict[str, Any],
    accounts: dict[str, dict[str, Any]],
    media_url: str,
) -> dict[str, Any]:
    targets = _snapshot_platforms(snapshot, accounts)
    # Zernio requires top-level content. Per-target customContent remains
    # authoritative, so this is only a safe shared fallback for validation.
    shared_content = next(
        (str(target.get("customContent") or "").strip() for target in targets if str(target.get("customContent") or "").strip()),
        str(snapshot.get("youtube_title") or "ClipKaro Short").strip() or "ClipKaro Short",
    )
    payload: dict[str, Any] = {
        "content": shared_content,
        "mediaItems": [{"type": "video", "url": media_url}],
        "platforms": targets,
    }
    youtube_tags = [str(x).lstrip("#").strip() for x in snapshot.get("youtube_tags") or [] if str(x).strip()]
    if youtube_tags:
        payload["tags"] = youtube_tags
    if snapshot.get("mode") == "schedule":
        payload["scheduledFor"] = snapshot.get("scheduled_for")
        payload["timezone"] = snapshot.get("timezone") or "Asia/Kolkata"
    else:
        payload["publishNow"] = True
    return payload


def _post_response(payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    post = payload.get("post") or payload.get("existingPost") or {}
    if not isinstance(post, dict):
        post = {}
    provider_post_id = str(post.get("_id") or post.get("id") or "").strip()
    status = str(post.get("status") or "").strip().lower()
    platforms = post.get("platforms") or payload.get("platformResults") or []
    raw_results = [item for item in platforms if isinstance(item, dict)] if isinstance(platforms, list) else []
    results: list[dict[str, Any]] = []
    for item in raw_results:
        normalized = dict(item)
        if not normalized.get("error"):
            normalized["error"] = normalized.get("errorMessage") or normalized.get("message")
        results.append(normalized)
    if status not in {"scheduled", "published", "partial", "failed", "processing"}:
        if results and all(str(item.get("status") or "").lower() == "published" for item in results):
            status = "published"
        elif any(str(item.get("status") or "").lower() == "failed" for item in results):
            status = "partial" if any(str(item.get("status") or "").lower() == "published" for item in results) else "failed"
        else:
            status = "processing"
    return status, provider_post_id, results


async def _materialize_export(
    export: dict[str, Any],
    user_id: str,
    destination: Path,
    *,
    storage: Any | None = None,
) -> Path:
    settings = get_settings()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if settings.normalized_storage_backend == "gcs":
        provider = storage or get_storage_provider()
        key = validate_object_key(
            str(export.get("output_path") or ""),
            expected_prefix=f"users/{user_id}/exports/{export['id']}",
        )
        metadata = await provider.stat(key)
        if not metadata or metadata.size <= 0:
            raise PostKaroProviderError("This finished Short is no longer available. Export it again.", status_code=410)
        generation = str(export.get("object_generation") or "")
        if generation and metadata.generation and generation != metadata.generation:
            raise PostKaroProviderError("This finished Short changed in storage. Export it again.", status_code=409)
        await provider.download(key, destination, generation=generation or None)
        return destination
    path = confined_export_path(export.get("output_path"))
    if not path or not path.is_file():
        raise PostKaroProviderError("This finished Short is no longer available. Export it again.", status_code=410)
    await asyncio.to_thread(shutil.copyfile, path, destination)
    return destination


def _expired(expires_at: Any) -> bool:
    try:
        value = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


async def run_publication_job(
    job_id: str,
    publication_id: str,
    *,
    scratch: Path | None = None,
    storage: Any | None = None,
) -> None:
    publication = await fetch_one(
        "SELECT * FROM post_karo_publications WHERE id=?", (publication_id,)
    )
    if not publication:
        raise RuntimeError("Post Karo publication no longer exists.")
    if publication.get("status") in {"scheduled", "published", "partial"}:
        await update_job(job_id, 100, "ready", "Post Karo handoff complete", "completed")
        return

    connection = await fetch_one(
        "SELECT * FROM post_karo_connections WHERE user_id=?", (publication["user_id"],)
    )
    if not connection:
        raise PostKaroProviderError("Post Karo is not connected. Reconnect it before posting.", status_code=409)
    api_key = decrypt_api_key(str(connection["api_key_ciphertext"]))
    snapshot = json.loads(str(publication.get("snapshot_json") or "{}"))
    accounts_list = await fetch_all(
        "SELECT * FROM post_karo_accounts WHERE user_id=?", (publication["user_id"],)
    )
    accounts = {str(row["platform"]): row for row in accounts_list}
    export = await fetch_one(
        "SELECT * FROM exports WHERE id=? AND user_id=?",
        (publication["export_id"], publication["user_id"]),
    )
    if not export or export.get("status") != "ready" or _expired(export.get("expires_at")):
        raise PostKaroProviderError("This Short has expired. Export it again before using Post Karo.", status_code=410)

    await execute(
        "UPDATE post_karo_publications SET status='processing',error=NULL,updated_at=? WHERE id=?",
        (utcnow(), publication_id),
    )
    await update_job(job_id, 8, "preparing", "Preparing your exact saved Short")
    owned_temp: tempfile.TemporaryDirectory | None = None
    try:
        if scratch is None:
            owned_temp = tempfile.TemporaryDirectory(prefix="clipkaro-post-karo-")
            workdir = Path(owned_temp.name)
        else:
            workdir = scratch / "post-karo"
            workdir.mkdir(parents=True, exist_ok=True)
        media_file = workdir / f"{publication['export_id']}.mp4"
        await _materialize_export(export, str(publication["user_id"]), media_file, storage=storage)
        await update_job(job_id, 32, "uploading", "Sending the finished Short securely")
        client = ZernioClient(api_key)
        media_url = await client.upload_media(media_file)
        await update_job(job_id, 66, "publishing", "Handing off to your selected social accounts")

        snapshot["mode"] = publication["mode"]
        snapshot["scheduled_for"] = publication.get("scheduled_for")
        payload = build_post_payload(snapshot, accounts, media_url)
        _, response = await client.create_post(payload, request_id=str(publication["request_id"]))
        provider_status, provider_post_id, results = _post_response(response)
        if publication["mode"] == "schedule" and provider_status == "processing":
            provider_status = "scheduled"
        final_status = provider_status if provider_status in {"scheduled", "published", "partial", "failed"} else "processing"
        await execute(
            """UPDATE post_karo_publications SET
                 status=?,provider_post_id=?,platform_results_json=?,error=NULL,updated_at=?
               WHERE id=?""",
            (
                final_status, provider_post_id,
                json.dumps(results, separators=(",", ":"), ensure_ascii=False),
                utcnow(), publication_id,
            ),
        )
        message = "Post Karo scheduled" if final_status == "scheduled" else "Post Karo handoff complete"
        job_status = "failed" if final_status == "failed" else "completed"
        await update_job(
            job_id, 100 if job_status == "completed" else 0,
            "ready" if job_status == "completed" else "failed",
            message if job_status == "completed" else "Publishing failed",
            job_status,
            None if job_status == "completed" else "One or more platforms rejected the post.",
        )
    except Exception as exc:
        if isinstance(exc, PostKaroProviderError):
            public_message = exc.public_message
        else:
            # Internal exception strings can contain paths, ids, provider
            # diagnostics or request details. Log them server-side only.
            logger.exception("Post Karo publication failed publication_id=%s", publication_id)
            public_message = "Post Karo could not finish publishing. Your ClipKaro Short is still safe. Retry shortly."
        await execute(
            "UPDATE post_karo_publications SET status='failed',error=?,updated_at=? WHERE id=?",
            (public_message, utcnow(), publication_id),
        )
        await update_job(job_id, 0, "failed", "Publishing failed", "failed", public_message)
        raise
    finally:
        if owned_temp is not None:
            owned_temp.cleanup()

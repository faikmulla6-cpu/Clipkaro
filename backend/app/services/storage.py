from __future__ import annotations

import asyncio
import mimetypes
import re
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

_SAFE_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,900}$")


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    size: int
    content_type: str
    generation: str


class StorageProvider(Protocol):
    async def stat(self, key: str) -> ObjectMetadata | None: ...
    async def download(self, key: str, destination: Path, *, generation: str | None = None) -> None: ...
    async def upload(self, source: Path, key: str, *, content_type: str) -> ObjectMetadata: ...
    async def delete(self, key: str, *, generation: str | None = None) -> bool: ...
    async def signed_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str: ...
    async def signed_download_url(self, key: str, *, filename: str, ttl_seconds: int) -> str: ...


def validate_object_key(key: str, *, expected_prefix: str | None = None) -> str:
    value = str(key or "").strip().replace("\\", "/")
    if not _SAFE_KEY.fullmatch(value) or ".." in value.split("/") or value.startswith("/"):
        raise ValueError("Invalid private object key.")
    if expected_prefix and not value.startswith(expected_prefix.rstrip("/") + "/"):
        raise ValueError("Object key is outside the authorized prefix.")
    return value


class LocalStorageProvider:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_settings().storage_root).resolve()

    def _path(self, key: str) -> Path:
        target = (self.root / validate_object_key(key)).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Object key escaped local private storage.")
        return target

    async def stat(self, key: str) -> ObjectMetadata | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return ObjectMetadata(key, path.stat().st_size, mimetypes.guess_type(path.name)[0] or "application/octet-stream", str(path.stat().st_mtime_ns))

    async def download(self, key: str, destination: Path, *, generation: str | None = None) -> None:
        source = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)

    async def upload(self, source: Path, key: str, *, content_type: str) -> ObjectMetadata:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, target)
        return ObjectMetadata(key, target.stat().st_size, content_type, str(target.stat().st_mtime_ns))

    async def delete(self, key: str, *, generation: str | None = None) -> bool:
        path = self._path(key)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    async def signed_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str:
        raise RuntimeError("Signed browser upload is available only with STORAGE_BACKEND=gcs.")

    async def signed_download_url(self, key: str, *, filename: str, ttl_seconds: int) -> str:
        raise RuntimeError("Signed browser download is available only with STORAGE_BACKEND=gcs.")


class GCSStorageProvider:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gcs_bucket.strip():
            raise RuntimeError("GCS_BUCKET is required for GCS storage.")
        from google.cloud import storage
        self.client = storage.Client(project=settings.gcp_project_id or None)
        self.bucket = self.client.bucket(settings.gcs_bucket)

    def _blob(self, key: str, generation: str | None = None):
        return self.bucket.blob(validate_object_key(key), generation=int(generation) if generation else None)

    async def stat(self, key: str) -> ObjectMetadata | None:
        blob = self._blob(key)
        try:
            await asyncio.to_thread(blob.reload)
        except Exception as exc:
            if exc.__class__.__name__ == "NotFound":
                return None
            raise
        return ObjectMetadata(key, int(blob.size or 0), str(blob.content_type or "application/octet-stream"), str(blob.generation or ""))

    async def download(self, key: str, destination: Path, *, generation: str | None = None) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._blob(key, generation).download_to_filename, str(destination))

    async def upload(self, source: Path, key: str, *, content_type: str) -> ObjectMetadata:
        blob = self._blob(key)
        await asyncio.to_thread(blob.upload_from_filename, str(source), content_type=content_type, if_generation_match=0)
        await asyncio.to_thread(blob.reload)
        return ObjectMetadata(key, int(blob.size or 0), str(blob.content_type or content_type), str(blob.generation or ""))

    async def delete(self, key: str, *, generation: str | None = None) -> bool:
        try:
            kwargs = {"if_generation_match": int(generation)} if generation else {}
            await asyncio.to_thread(self._blob(key, generation).delete, **kwargs)
            return True
        except Exception as exc:
            if exc.__class__.__name__ == "NotFound":
                return False
            raise

    def _signed(self, blob, *, method: str, ttl_seconds: int, content_type: str | None = None, disposition: str | None = None) -> str:
        settings = get_settings()
        kwargs = {"version": "v4", "expiration": timedelta(seconds=ttl_seconds), "method": method}
        if content_type:
            kwargs["content_type"] = content_type
        if disposition:
            kwargs["response_disposition"] = disposition
        if settings.gcs_signing_service_account:
            from google.auth import default
            from google.auth import impersonated_credentials
            credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            signing_credentials = impersonated_credentials.Credentials(
                source_credentials=credentials,
                target_principal=settings.gcs_signing_service_account,
                target_scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
                lifetime=900,
            )
            kwargs.update(credentials=signing_credentials, service_account_email=settings.gcs_signing_service_account)
        return blob.generate_signed_url(**kwargs)

    async def signed_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str:
        return await asyncio.to_thread(self._signed, self._blob(key), method="PUT", ttl_seconds=ttl_seconds, content_type=content_type)

    async def signed_download_url(self, key: str, *, filename: str, ttl_seconds: int) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120] or "clipkaro-short.mp4"
        return await asyncio.to_thread(self._signed, self._blob(key), method="GET", ttl_seconds=ttl_seconds, disposition=f'attachment; filename="{safe_name}"')


def get_storage_provider() -> StorageProvider:
    return GCSStorageProvider() if get_settings().normalized_storage_backend == "gcs" else LocalStorageProvider()

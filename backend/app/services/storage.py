from __future__ import annotations

import asyncio
import mimetypes
import os
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


def object_storage_provider_name() -> str:
    """Return the concrete cloud object provider without changing local-dev contracts.

    `STORAGE_BACKEND=gcs` remains the compatibility selector for the existing
    serverless code path. Modal deployments set `OBJECT_STORAGE_PROVIDER=s3`,
    which swaps only the provider adapter while preserving the established
    upload/session/business contracts.
    """
    configured = os.environ.get("OBJECT_STORAGE_PROVIDER", "").strip().lower()
    if configured:
        if configured not in {"gcs", "s3"}:
            raise RuntimeError("OBJECT_STORAGE_PROVIDER must be 'gcs' or 's3'.")
        return configured
    return "gcs" if get_settings().normalized_storage_backend == "gcs" else "local"


def cloud_object_storage_enabled() -> bool:
    return get_settings().normalized_storage_backend == "gcs" and object_storage_provider_name() in {"gcs", "s3"}


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
        raise RuntimeError("Signed browser upload is available only with cloud object storage.")

    async def signed_download_url(self, key: str, *, filename: str, ttl_seconds: int) -> str:
        raise RuntimeError("Signed browser download is available only with cloud object storage.")


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


class S3StorageProvider:
    """Private S3-compatible storage adapter used by Backblaze B2 on Modal.

    Durable database state continues to store object keys, never public URLs.
    Browser access is authorized only with short-lived SigV4 URLs.
    """

    def __init__(self) -> None:
        endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip().rstrip("/")
        region = os.environ.get("S3_REGION", "").strip()
        bucket = os.environ.get("S3_BUCKET_NAME", "").strip()
        key_id = os.environ.get("S3_ACCESS_KEY_ID", "").strip()
        secret = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip()
        if not endpoint.startswith("https://"):
            raise RuntimeError("S3_ENDPOINT_URL must be an HTTPS endpoint.")
        if not all((region, bucket, key_id, secret)):
            raise RuntimeError("S3-compatible storage configuration is incomplete.")
        import boto3
        from botocore.config import Config
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @staticmethod
    def _generation(response: dict) -> str:
        version = str(response.get("VersionId") or "").strip()
        if version:
            return "version:" + version
        etag = str(response.get("ETag") or "").strip().strip('"')
        return "etag:" + etag if etag else ""

    async def stat(self, key: str) -> ObjectMetadata | None:
        safe_key = validate_object_key(key)
        try:
            response = await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=safe_key)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "get", lambda *_: {}) ("ResponseMetadata", {}).get("HTTPStatusCode") if getattr(exc, "response", None) else None
            code = str((getattr(exc, "response", {}) or {}).get("Error", {}).get("Code", ""))
            if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectMetadata(
            safe_key,
            int(response.get("ContentLength") or 0),
            str(response.get("ContentType") or "application/octet-stream"),
            self._generation(response),
        )

    async def download(self, key: str, destination: Path, *, generation: str | None = None) -> None:
        safe_key = validate_object_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        extra = {"VersionId": generation.removeprefix("version:")} if generation and generation.startswith("version:") else None
        if extra:
            await asyncio.to_thread(self.client.download_file, self.bucket, safe_key, str(destination), ExtraArgs=extra)
        else:
            await asyncio.to_thread(self.client.download_file, self.bucket, safe_key, str(destination))

    async def upload(self, source: Path, key: str, *, content_type: str) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        await asyncio.to_thread(
            self.client.upload_file,
            str(source), self.bucket, safe_key,
            ExtraArgs={"ContentType": content_type},
        )
        metadata = await self.stat(safe_key)
        if metadata is None:
            raise RuntimeError("S3 upload completed without readable metadata.")
        return metadata

    async def delete(self, key: str, *, generation: str | None = None) -> bool:
        safe_key = validate_object_key(key)
        current = await self.stat(safe_key)
        if current is None:
            return False
        if generation and current.generation and generation != current.generation:
            return False
        kwargs = {"Bucket": self.bucket, "Key": safe_key}
        if generation and generation.startswith("version:"):
            kwargs["VersionId"] = generation.removeprefix("version:")
        await asyncio.to_thread(self.client.delete_object, **kwargs)
        return True

    async def signed_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str:
        safe_key = validate_object_key(key)
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self.bucket, "Key": safe_key, "ContentType": content_type},
            ExpiresIn=max(60, min(int(ttl_seconds), 3600)),
            HttpMethod="PUT",
        )

    async def signed_download_url(self, key: str, *, filename: str, ttl_seconds: int) -> str:
        safe_key = validate_object_key(key)
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120] or "clipkaro-short.mp4"
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": safe_key,
                "ResponseContentDisposition": f'attachment; filename="{safe_name}"',
            },
            ExpiresIn=max(60, min(int(ttl_seconds), 3600)),
            HttpMethod="GET",
        )


def get_storage_provider() -> StorageProvider:
    settings = get_settings()
    if settings.normalized_storage_backend != "gcs":
        return LocalStorageProvider()
    provider = object_storage_provider_name()
    if provider == "s3":
        return S3StorageProvider()
    return GCSStorageProvider()

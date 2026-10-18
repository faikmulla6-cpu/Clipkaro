"""Purge private Smart Layout v2 artifacts when source media is deleted.

Unlike source uploads, a clip may have many historical trim/generation keys.
Deleting only the latest hash would strand older face-position metadata.
This deletion is strictly limited to one authorized project's Smart Layout
namespace; no source, export or other customer's object may be deleted.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from pathlib import Path

from app.services.smart_layout_cache import safe_owner_key
from app.services.storage import S3StorageProvider, LocalStorageProvider

MAX_VERSIONS = 5000


def _scope(user_id: str, project_id: str) -> str:
    try:
        u, p = str(uuid.UUID(str(user_id))), str(uuid.UUID(str(project_id)))
        if str(u) != str(user_id) or str(p) != str(project_id):
            raise ValueError("Noncanonical owner identifiers")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Unsafe Smart Layout cleanup owner") from exc
    return f"users/{u}/projects/{p}/smart-layout/v2/"


async def purge_smart_layout_plans(storage, user_id: str, project_id: str) -> int:
    prefix = _scope(user_id, project_id)
    if isinstance(storage, LocalStorageProvider):
        root = Path(storage.root).resolve()
        target = (root / prefix).resolve()
        if target == root or root not in target.parents:
            raise ValueError("Unsafe local Smart Layout cleanup path")
        if not target.exists():
            return 0
        if target.is_symlink():
            raise ValueError("Refusing to follow a storage symlink")
        count = len(list(target.glob("*/*.json")))
        await asyncio.to_thread(shutil.rmtree, target)
        return count
    if not isinstance(storage, S3StorageProvider):
        raise RuntimeError("Unsupported private Smart Layout cleanup storage")

    # Backblaze B2 objects may be versioned. ListObjectVersions and delete the
    # EXACT VersionIds so previous iterations cannot outlive deletion.
    marker_key = None
    marker_version = None
    removed = 0
    while True:
        kwargs = {"Bucket": storage.bucket, "Prefix": prefix, "MaxKeys": 1000}
        if marker_key:
            kwargs["KeyMarker"] = marker_key
        if marker_version:
            kwargs["VersionIdMarker"] = marker_version
        result = await asyncio.to_thread(storage.client.list_object_versions, **kwargs)
        entries = list(result.get("Versions") or []) + list(result.get("DeleteMarkers") or [])
        # Validate the WHOLE returned page before deleting any entry. A
        # malicious/misconfigured B2 listing must never partly delete another
        # namespace before the bad key is encountered.
        for entry in entries:
            key = str(entry.get("Key") or "")
            version = str(entry.get("VersionId") or "")
            if not safe_owner_key(key, user_id, project_id) or not version:
                raise ValueError("Unexpected object outside Smart Layout private namespace")
        if removed + len(entries) > MAX_VERSIONS:
            raise RuntimeError("Too many cache versions; manual review required")
        for entry in entries:
            await asyncio.to_thread(storage.client.delete_object, Bucket=storage.bucket,
                                    Key=str(entry["Key"]), VersionId=str(entry["VersionId"]))
            removed += 1
        if not result.get("IsTruncated"):
            return removed
        new_key = result.get("NextKeyMarker")
        new_version = result.get("NextVersionIdMarker")
        if not new_key or (new_key, new_version) == (marker_key, marker_version):
            raise RuntimeError("Smart Layout cache deletion could not advance safely")
        marker_key, marker_version = str(new_key), str(new_version) if new_version else None

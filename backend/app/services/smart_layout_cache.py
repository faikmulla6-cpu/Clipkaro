"""Private, versioned layout analysis keys with source and clip invalidation.

Callers MUST derive these values from authenticated database rows, never from
client-supplied key strings. This module has no network or storage side effects.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass

ANALYSIS_SCHEMA = "v2"
MODEL_VERSION = "opencv-scene-20261030-cutguard-v7"


def _uuid(value: str, name: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(name + " must be a valid identifier") from exc
    if parsed.version not in (4, 7):
        raise ValueError(name + " must be an approved generated identifier")
    return str(parsed)


def _second(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(label + " must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(label + " must be numeric") from exc
    if not math.isfinite(result) or result < 0 or result > 86400:
        raise ValueError(label + " outside safe time range")
    return result


@dataclass(frozen=True)
class AnalysisIdentity:
    user_id: str
    project_id: str
    clip_id: str
    video_id: str
    generation: str
    start: float
    end: float

    def validated(self) -> "AnalysisIdentity":
        uid = _uuid(self.user_id, "user_id")
        pid = _uuid(self.project_id, "project_id")
        cid = _uuid(self.clip_id, "clip_id")
        vid = _uuid(self.video_id, "video_id")
        start = _second(self.start, "start")
        end = _second(self.end, "end")
        if end - start < .1 or end - start > 180:
            raise ValueError("Clip duration must be within 0.1 to 180 seconds")
        generation = str(self.generation or "").strip()
        if not generation or len(generation) > 160:
            raise ValueError("A confirmed source generation is required")
        if any(ord(char) < 32 or char in (chr(92), '/') for char in generation):
            raise ValueError("Invalid source generation")
        return AnalysisIdentity(uid, pid, cid, vid, generation,
                                round(start, 4), round(end, 4))


def private_plan_key(identity: AnalysisIdentity) -> str:
    """Return only a private B2 key: never a signed URL or public identifier.

    The SHA-256 fingerprint includes the exact source generation, video and
    clip range so a re-upload, trim, or different source invalidates old work.
    Different users and projects cannot share the same cache path.
    """
    item = identity.validated()
    fingerprint = json.dumps(
        {
            "schema": ANALYSIS_SCHEMA,
            "model": MODEL_VERSION,
            "video": item.video_id,
            "generation": item.generation,
            "start": item.start,
            "end": item.end,
        }, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(fingerprint).hexdigest()
    return (f"users/{item.user_id}/projects/{item.project_id}/smart-layout/"
            f"{ANALYSIS_SCHEMA}/{item.clip_id}/{digest}.json")


def safe_owner_key(key: str, user_id: str, project_id: str) -> bool:
    """Defense in depth: a cache key must stay in this customer's namespace."""
    try:
        prefix = ("users/" + _uuid(user_id, "user_id") +
                  "/projects/" + _uuid(project_id, "project_id") +
                  "/smart-layout/" + ANALYSIS_SCHEMA + "/")
        if not isinstance(key, str) or not key.startswith(prefix) or len(key) >= 450:
            return False
        suffix = key[len(prefix):]
        parts = suffix.split("/")
        if len(parts) != 2 or parts[0] != _uuid(parts[0], "clip_id"):
            return False
        return (len(parts[1]) == 69 and parts[1].endswith(".json") and
                all(c in "0123456789abcdef" for c in parts[1][:64]))
    except ValueError:
        return False

"""Regression tests for generation-locked R2/S3 media downloads (no cloud calls)."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.services.storage import S3StorageProvider


SOURCE_KEY = "quarantine/creator/upload/source.mp4"


class FakeR2:
    def __init__(self, payload: bytes = b"original-media", etag: str = "original-etag"):
        self.payload = payload
        self.etag = etag
        self.response_etag = etag
        self.declared_length = len(payload)
        self.get_calls: list[dict] = []
        self.fallback_calls: list[tuple] = []

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)
        if kwargs.get("IfMatch") != f'"{self.etag}"':
            raise RuntimeError("412 PreconditionFailed: source object was replaced")
        return {
            "ETag": f'"{self.response_etag}"',
            "ContentLength": self.declared_length,
            "Body": io.BytesIO(self.payload),
        }

    def download_file(self, bucket, key, destination, **kwargs):
        self.fallback_calls.append((bucket, key, destination, kwargs))
        Path(destination).write_bytes(self.payload)


def provider_with(fake: FakeR2) -> S3StorageProvider:
    provider = object.__new__(S3StorageProvider)
    provider.bucket = "private-r2"
    provider.client = fake
    return provider


@pytest.mark.asyncio
async def test_etag_locked_download_matches_confirmed_source(tmp_path):
    fake = FakeR2()
    destination = tmp_path / "source.mp4"

    await provider_with(fake).download(SOURCE_KEY, destination, generation="etag:original-etag")

    assert destination.read_bytes() == b"original-media"
    assert fake.get_calls == [{
        "Bucket": "private-r2",
        "Key": SOURCE_KEY,
        "IfMatch": '"original-etag"',
    }]
    assert not fake.fallback_calls
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.asyncio
async def test_replaced_same_size_r2_object_is_rejected_before_processing(tmp_path):
    # The upload-complete DB generation still points at A; the signed PUT
    # has overwritten the key with different, same-sized video bytes B.
    fake = FakeR2(payload=b"changed!-media", etag="etag-of-video-b")
    assert len(fake.payload) == len(b"original-media")
    destination = tmp_path / "source.mp4"

    with pytest.raises(RuntimeError, match="412 PreconditionFailed"):
        await provider_with(fake).download(SOURCE_KEY, destination, generation="etag:etag-of-video-a")

    assert not destination.exists()
    assert not list(tmp_path.iterdir())
    assert not fake.fallback_calls


@pytest.mark.asyncio
async def test_get_response_must_match_pinned_etag_even_if_provider_accepts_condition(tmp_path):
    fake = FakeR2()
    fake.response_etag = "other-etag"
    destination = tmp_path / "source.mp4"

    with pytest.raises(RuntimeError, match="Source ETag changed"):
        await provider_with(fake).download(SOURCE_KEY, destination, generation="etag:original-etag")

    assert not destination.exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_incomplete_conditional_stream_never_publishes_partial_destination(tmp_path):
    fake = FakeR2(payload=b"partial-video")
    fake.declared_length = len(fake.payload) + 8
    destination = tmp_path / "source.mp4"
    destination.write_bytes(b"previous-safe-file")

    with pytest.raises(RuntimeError, match="incomplete"):
        await provider_with(fake).download(SOURCE_KEY, destination, generation="etag:original-etag")

    assert destination.read_bytes() == b"previous-safe-file"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.asyncio
async def test_oversized_conditional_stream_is_rejected_and_cleaned(tmp_path):
    fake = FakeR2(payload=b"too-many-bytes")
    fake.declared_length = 3
    destination = tmp_path / "source.mp4"

    with pytest.raises(RuntimeError, match="exceeded verified length"):
        await provider_with(fake).download(SOURCE_KEY, destination, generation="etag:original-etag")

    assert not destination.exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_version_pinned_and_unpinned_legacy_downloads_preserved(tmp_path):
    fake = FakeR2()
    provider = provider_with(fake)
    versioned = tmp_path / "version.mp4"
    legacy = tmp_path / "legacy.mp4"

    await provider.download(SOURCE_KEY, versioned, generation="version:stored-version")
    await provider.download(SOURCE_KEY, legacy)

    assert versioned.read_bytes() == fake.payload
    assert legacy.read_bytes() == fake.payload
    assert fake.fallback_calls[0][3] == {"ExtraArgs": {"VersionId": "stored-version"}}
    assert fake.fallback_calls[1][3] == {}
    assert not fake.get_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("generation", ["etag:", "etag:bad\nheader", "multipart:uncommitted"])
async def test_bad_generation_fails_without_unconditional_download(tmp_path, generation):
    fake = FakeR2()
    destination = tmp_path / "source.mp4"

    with pytest.raises(ValueError):
        await provider_with(fake).download(SOURCE_KEY, destination, generation=generation)

    assert not destination.exists()
    assert not fake.get_calls
    assert not fake.fallback_calls

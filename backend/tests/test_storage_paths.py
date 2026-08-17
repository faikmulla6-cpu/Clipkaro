from __future__ import annotations

from types import SimpleNamespace

from app.services import storage_paths


def test_confined_storage_path_accepts_only_requested_media_area(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    uploads = root / "uploads"
    exports = root / "exports"
    uploads.mkdir(parents=True)
    exports.mkdir(parents=True)
    upload = uploads / "video.mp4"
    export = exports / "short.mp4"
    outside = tmp_path / "outside.mp4"
    upload.write_bytes(b"upload")
    export.write_bytes(b"export")
    outside.write_bytes(b"outside")

    monkeypatch.setattr(storage_paths, "get_settings", lambda: SimpleNamespace(storage_root=root))

    assert storage_paths.confined_upload_path(upload) == upload.resolve()
    assert storage_paths.confined_export_path(export) == export.resolve()
    assert storage_paths.confined_upload_path(export) is None
    assert storage_paths.confined_export_path(upload) is None
    assert storage_paths.confined_upload_path(outside) is None
    assert storage_paths.confined_export_path(outside) is None


def test_confined_storage_path_rejects_parent_traversal(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    (root / "uploads").mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    monkeypatch.setattr(storage_paths, "get_settings", lambda: SimpleNamespace(storage_root=root))

    traversal = root / "uploads" / ".." / ".." / "outside.mp4"
    assert storage_paths.confined_upload_path(traversal) is None


def test_confined_storage_path_rejects_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    uploads = root / "uploads"
    uploads.mkdir(parents=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "private.mp4"
    outside_file.write_bytes(b"outside")
    link = uploads / "linked"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        return

    monkeypatch.setattr(storage_paths, "get_settings", lambda: SimpleNamespace(storage_root=root))
    assert storage_paths.confined_upload_path(link / "private.mp4") is None

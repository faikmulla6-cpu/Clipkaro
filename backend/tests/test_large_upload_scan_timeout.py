from types import SimpleNamespace

from app.services.upload_scanner import _local_scan_timeout_seconds


class Media:
    def __init__(self, size_mb):
        self.size_mb = size_mb

    def stat(self):
        return SimpleNamespace(st_size=self.size_mb * 1024 * 1024)


def test_scanner_timeout_grows_with_upload_but_is_always_bounded():
    assert _local_scan_timeout_seconds(Media(10)) >= 30
    assert _local_scan_timeout_seconds(Media(500)) >= 600
    assert _local_scan_timeout_seconds(Media(4096)) == 2400
    assert _local_scan_timeout_seconds(Media(10000)) == 2400

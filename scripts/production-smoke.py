#!/usr/bin/env python3
"""Secret-free public smoke test for a deployed ClipKaro edge.

Usage:
    python scripts/production-smoke.py https://your-domain.example

This intentionally performs no login, payment, upload, or provider calls.
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse


def fail(message: str) -> None:
    print(f"FAIL  {message}")
    raise SystemExit(1)


def fetch(url: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "ClipKaro-Launch-Smoke/1.0"})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=12, context=context) as response:
        return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(512 * 1024)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/production-smoke.py https://your-domain.example", file=sys.stderr)
        return 2
    base = sys.argv[1].rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname:
        fail("base URL must be an HTTPS origin")

    checks = [
        ("web", f"{base}/", False),
        ("api health", f"{base}/api/v1/health", True),
        ("public legal config", f"{base}/api/v1/legal/config", True),
    ]
    all_headers: list[dict[str, str]] = []
    for label, url, expect_json in checks:
        try:
            status, headers, body = fetch(url)
        except urllib.error.HTTPError as exc:
            fail(f"{label}: HTTP {exc.code}")
        except Exception as exc:
            fail(f"{label}: request failed ({type(exc).__name__})")
        if status != 200:
            fail(f"{label}: expected 200, got {status}")
        if expect_json:
            try:
                json.loads(body.decode("utf-8"))
            except Exception:
                fail(f"{label}: response is not valid JSON")
        all_headers.append(headers)
        print(f"PASS  {label}")

    edge_headers = all_headers[0]
    required_headers = {
        "strict-transport-security": "HSTS",
        "x-content-type-options": "X-Content-Type-Options",
        "x-frame-options": "X-Frame-Options",
        "referrer-policy": "Referrer-Policy",
        "content-security-policy": "Content-Security-Policy",
    }
    for header, label in required_headers.items():
        if not edge_headers.get(header):
            fail(f"edge missing {label}")
        print(f"PASS  {label}")

    print("\nPublic production smoke: PASS")
    print("This does not validate authenticated upload, ASR, Razorpay, email, or webhook flows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

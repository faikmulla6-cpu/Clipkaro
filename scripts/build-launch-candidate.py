#!/usr/bin/env python3
"""Build and secret-scan a sanitized ClipKaro source launch candidate.

The script copies release source into a fresh directory, excludes private/runtime
state, scans the staged tree (not just the source tree), and creates a ZIP only
when release hygiene checks pass.

It never prints discovered secret values.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "ClipKaro-7.8.0-launch-candidate"

EXCLUDED_DIR_NAMES = {
    ".git", ".idea", ".vscode", ".next", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "env",
    "backups", "launch-qa", "launch-qa-attempt", "stress_corpus",
    "asr-qualification-evidence", "landscape_qa", "landscape-qualification-evidence",
}
EXCLUDED_DIR_PATHS = {
    "backend/storage",
    "backend/stress_corpus",
    "backend/landscape_qa",
    "backend/landscape-qualification-evidence",
    "docs/evidence",
}
EXCLUDED_FILE_NAMES = {
    "backend.env",
    "pytest-report.xml",
    "npm-audit-production.json",
    "asr-execution-preflight.json",
    "asr-runner-hardware.txt",
    "asr-verdict-trigger.txt",
    "landscape-qa-resource.txt",
    "landscape-execution-preflight.json",
    "landscape-runner-hardware.txt",
}
EXCLUDED_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".log", ".mp4", ".mov",
    ".mkv", ".webm", ".wav", ".m4a", ".mp3", ".flac", ".aac", ".ttf", ".otf", ".woff", ".woff2",
}
ALLOWED_ENV_FILES = {
    ".env.production.example",
    "backend/.env.example",
    "frontend/.env.example",
}
TEXT_SUFFIXES = {
    "", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json",
    ".md", ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".css", ".scss", ".html", ".xml", ".sh", ".ps1", ".example",
}
SENSITIVE_NAME = re.compile(
    r"(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|ACCOUNT_ID|USER_IDS|PRIVATE|CREDENTIAL)",
    re.I,
)
MACHINE_PATH_PATTERNS = [
    ("Windows user path", re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|Downloads)[\\/]", re.I)),
    ("macOS user path", re.compile(r"/" + r"Users/[^/\s]+/", re.I)),
]

GENERIC_SECRET_PATTERNS = [
    ("Razorpay live key id", re.compile(r"rzp_live_[A-Za-z0-9]{10,}")),
    ("Groq key", re.compile(r"gsk_[A-Za-z0-9_-]{20,}")),
    ("Resend key", re.compile(r"(?<![A-Za-z0-9_])re_[A-Za-z0-9_-]{20,}")),
    ("generic sk key", re.compile(r"(?<![A-Za-z0-9])sk_[A-Za-z0-9_-]{24,}")),
]


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_env_file(rel: str, name: str) -> bool:
    return name == ".env" or name.startswith(".env.") or rel == "backend.env"


def excluded(path: Path, *, is_dir: bool) -> bool:
    rel = relative(path)
    if is_dir:
        if path.name in EXCLUDED_DIR_NAMES:
            return True
        return any(rel == item or rel.startswith(item + "/") for item in EXCLUDED_DIR_PATHS)
    if path.name in EXCLUDED_FILE_NAMES or rel in EXCLUDED_FILE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if is_env_file(rel, path.name) and rel not in ALLOWED_ENV_FILES:
        return True
    if path.name.startswith("asr-stress-report") and path.suffix == ".json":
        return True
    return False


def copy_release(destination: Path) -> int:
    count = 0
    for base, dirs, files in os.walk(ROOT):
        base_path = Path(base)
        dirs[:] = [name for name in dirs if not excluded(base_path / name, is_dir=True)]
        for name in files:
            source = base_path / name
            if excluded(source, is_dir=False):
                continue
            rel = source.relative_to(ROOT)
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            count += 1
    return count


def private_env_values() -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for env_path in (ROOT / "backend/.env", ROOT / ".env", ROOT / "frontend/.env.local"):
        if not env_path.exists():
            continue
        try:
            lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if not value or len(value) < 8 or not SENSITIVE_NAME.search(key):
                continue
            # Development fixture identities intentionally appear in source/tests
            # and are not private deployment identities. Real allowlist IDs and
            # credentials are still exact-match scanned from the private env.
            if value.lower() in {"demo-user", "test-user", "example-user"}:
                continue
            values.append((key.strip(), value))
    return values


def looks_textual(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in chunk


def obviously_fixture(text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 120): min(len(text), end + 120)].lower()
    return any(word in context for word in ("fake", "dummy", "example", "placeholder", "test_", "test-", "mock"))


def scan_stage(destination: Path) -> list[str]:
    issues: list[str] = []
    known = private_env_values()
    for path in destination.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(destination).as_posix()
        # Structural hygiene first.
        if is_env_file(rel, path.name) and rel not in ALLOWED_ENV_FILES:
            issues.append(f"private environment file staged: {rel}")
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            issues.append(f"runtime/private file staged: {rel}")
        if not looks_textual(path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for key, value in known:
            if value in content:
                issues.append(f"known local secret/identity value from {key} found in {rel}")
        for label, pattern in MACHINE_PATH_PATTERNS:
            if pattern.search(content):
                issues.append(f"developer-machine {label} found in {rel}")
        for label, pattern in GENERIC_SECRET_PATTERNS:
            for match in pattern.finditer(content):
                if obviously_fixture(content, match.start(), match.end()):
                    continue
                issues.append(f"possible {label} found in {rel}")
                break
    return sorted(set(issues))


def make_zip(source: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=f"{source.name}/{path.relative_to(source).as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent / DEFAULT_NAME)
    parser.add_argument("--zip", dest="zip_path", type=Path, default=ROOT.parent / f"{DEFAULT_NAME}.zip")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    zip_path = args.zip_path.resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        print("ERROR: output directory must be outside the source repository", file=sys.stderr)
        return 2
    if output_dir.exists():
        shutil.rmtree(output_dir)
    if zip_path.exists():
        zip_path.unlink()
    output_dir.mkdir(parents=True)

    copied = copy_release(output_dir)
    issues = scan_stage(output_dir)
    if issues:
        print(f"Release hygiene scan: FAIL ({len(issues)} issue(s))")
        for issue in issues:
            print(f"- {issue}")
        shutil.rmtree(output_dir, ignore_errors=True)
        return 1

    make_zip(output_dir, zip_path)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    checksum_path = zip_path.with_suffix(zip_path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(f"Release hygiene scan: PASS")
    print(f"Files staged: {copied}")
    print(f"Directory: {output_dir}")
    print(f"ZIP: {zip_path}")
    print(f"SHA256: {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

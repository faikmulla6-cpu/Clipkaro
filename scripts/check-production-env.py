#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlparse

PLACEHOLDERS = ("replace", "placeholder", "__required", "example.com", "changeme", "dummy", "todo", "tbd")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE = re.compile(r"^\+?[0-9][0-9\s().-]{7,20}$")
PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def placeholder(value: str) -> bool:
    lower = value.strip().lower()
    return not lower or any(mark in lower for mark in PLACEHOLDERS)


def secret_ok(value: str, minimum: int) -> bool:
    return not placeholder(value) and len(value) >= minimum and len(set(value)) >= 12


def email_ok(value: str) -> bool:
    return not placeholder(value) and bool(EMAIL.fullmatch(value.strip()))


def mailbox_ok(value: str) -> bool:
    text = value.strip()
    if "<" in text and text.endswith(">"):
        text = text.rsplit("<", 1)[1][:-1].strip()
    return email_ok(text)


def phone_ok(value: str) -> bool:
    if placeholder(value) or not PHONE.fullmatch(value.strip()):
        return False
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def https_ok(value: str) -> bool:
    if placeholder(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname)


def validate(env: dict[str, str]) -> list[str]:
    b: list[str] = []
    get = lambda k: env.get(k, "").strip()
    if placeholder(get("DOMAIN")):
        b.append("DOMAIN_MISSING")
    if not email_ok(get("ACME_EMAIL")):
        b.append("ACME_EMAIL_INVALID")
    if not secret_ok(get("SECRET_KEY"), 32):
        b.append("SECRET_KEY_WEAK")
    if get("PRODUCTION_CREDENTIALS_ROTATED").lower() != "true":
        b.append("PRODUCTION_CREDENTIAL_ROTATION_UNCONFIRMED")
    if not https_ok(get("APP_PUBLIC_URL")):
        b.append("APP_PUBLIC_URL_NOT_HTTPS")
    if not https_ok(get("FRONTEND_URL")):
        b.append("FRONTEND_URL_NOT_HTTPS")
    domain = get("DOMAIN").lower().rstrip(".")
    for key in ("APP_PUBLIC_URL", "FRONTEND_URL"):
        try:
            host = (urlparse(get(key)).hostname or "").lower().rstrip(".")
        except ValueError:
            host = ""
        if domain and not placeholder(domain) and host and host != domain:
            b.append(f"{key}_DOMAIN_MISMATCH")
    seed_demo = get("SEED_DEMO_USER").lower()
    if seed_demo and seed_demo not in {"false", "0", "no", "off"}:
        b.append("SEED_DEMO_USER_ENABLED")

    resend_ready = secret_ok(get("RESEND_API_KEY"), 20) and mailbox_ok(get("EMAIL_FROM"))
    smtp_ready = (
        not placeholder(get("SMTP_HOST"))
        and mailbox_ok(get("SMTP_FROM_EMAIL") or get("EMAIL_FROM"))
        and bool(get("SMTP_USERNAME")) == bool(get("SMTP_PASSWORD"))
    )
    if not (resend_ready or smtp_ready):
        b.append("TRANSACTIONAL_EMAIL_NOT_CONFIGURED")

    if get("RAZORPAY_MODE").lower() != "live":
        b.append("RAZORPAY_MODE_NOT_LIVE")
    if get("ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT").lower() not in {"false", "0", "no", "off"}:
        b.append("LIVE_RAZORPAY_DEVELOPMENT_OPT_IN_ENABLED")
    if not get("RAZORPAY_KEY_ID").startswith("rzp_live_"):
        b.append("RAZORPAY_LIVE_KEY_ID_MISSING")
    if not secret_ok(get("RAZORPAY_KEY_SECRET"), 20):
        b.append("RAZORPAY_KEY_SECRET_MISSING")
    if not secret_ok(get("RAZORPAY_WEBHOOK_SECRET"), 32):
        b.append("RAZORPAY_WEBHOOK_SECRET_WEAK")

    asr_mode = get("ASR_MODE").lower()
    worker_target = get("WORKER_IMAGE_TARGET").lower()
    if asr_mode not in {"api", "local"}:
        b.append("ASR_MODE_INVALID")
    elif (asr_mode == "api" and worker_target != "api") or (asr_mode == "local" and worker_target != "worker"):
        b.append("WORKER_IMAGE_TARGET_ASR_MODE_MISMATCH")

    if get("HINGLISH_STAGE1_ENABLED").lower() in {"true", "1", "yes", "on"} and not get("HINGLISH_STAGE1_USER_IDS"):
        b.append("HINGLISH_STAGE1_ALLOWLIST_EMPTY")

    groq = [get(f"GROQ_API_KEY_{i}") for i in range(1, 6)]
    pool = get("GROQ_API_KEYS")
    if get("GROQ_RANKING_ENABLED").lower() != "false" and not any(groq) and not pool:
        b.append("GROQ_KEYS_MISSING")

    required_public = {
        "LEGAL_OPERATOR_NAME": lambda v: not placeholder(v) and len(v) >= 3,
        "LEGAL_OPERATOR_ADDRESS": lambda v: not placeholder(v) and len(v) >= 15 and " " in v,
        "LEGAL_CONTACT_EMAIL": email_ok,
        "PRIVACY_CONTACT_EMAIL": email_ok,
        "CUSTOMER_CARE_EMAIL": email_ok,
        "CUSTOMER_CARE_PHONE": phone_ok,
        "GRIEVANCE_OFFICER_NAME": lambda v: not placeholder(v) and len(v) >= 3,
        "GRIEVANCE_EMAIL": email_ok,
        "GRIEVANCE_PHONE": phone_ok,
    }
    for key, validator in required_public.items():
        if not validator(get(key)):
            b.append(key + "_INVALID")

    pan = get("LEGAL_PAN").upper()
    gstin = get("LEGAL_GSTIN").upper()
    if pan and not PAN.fullmatch(pan):
        b.append("LEGAL_PAN_INVALID")
    if gstin and not GSTIN.fullmatch(gstin):
        b.append("LEGAL_GSTIN_INVALID")
    return list(dict.fromkeys(b))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env-file", required=True, type=Path)
    p.add_argument("--require-ready", action="store_true")
    args = p.parse_args()
    env = read_env(args.env_file)
    blockers = validate(env)
    payload = {
        "ready_for_live_preflight": not blockers,
        "blockers": blockers,
        "note": (
            "Offline configuration checks passed. paid_launch_ready=true still requires live transactional email, Razorpay, ClamAV, worker/ASR and legal preflight checks."
            if not blockers
            else "Configuration remains fail-closed. Only blocker names are shown; secret values are never printed."
        ),
    }
    print(json.dumps(payload, indent=2))
    return 1 if args.require_ready and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import tempfile

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{7,20}$")
PLACEHOLDER = "__REQUIRED__"


def parse_credential_file(path: Path | None) -> dict[str, object]:
    result: dict[str, object] = {"groq": []}
    if not path:
        return result
    text = path.read_text(encoding="utf-8")
    result["groq"] = re.findall(r"(?im)^groq api key \d+\s*-\s*(\S+)\s*$", text)
    match = re.search(r"(?im)^RAZORPAY_KEY_ID=(\S+)\s*$", text)
    if match:
        result["razorpay_key_id"] = match.group(1)
    match = re.search(r"(?im)^RAZORPAY_KEY_SECRET=(\S+)\s*$", text)
    if match:
        result["razorpay_key_secret"] = match.group(1)
    return result


def ask(label: str, *, secret: bool = False, default: str = "", required: bool = True) -> str:
    prompt = f"{label}"
    if default and not secret:
        prompt += f" [{default}]"
    prompt += ": "
    reader = getpass.getpass if secret else input
    while True:
        value = reader(prompt).strip()
        if not value:
            value = default
        if value or not required:
            return value
        print(f"{label} is required.")


def build_env(imported: dict[str, object], *, draft: bool) -> dict[str, str]:
    generated_secret = secrets.token_urlsafe(64)
    generated_webhook = secrets.token_urlsafe(48)

    if draft:
        groq = list(imported.get("groq") or [])
        return {
            "DOMAIN": PLACEHOLDER,
            "ACME_EMAIL": "",
            "SECRET_KEY": generated_secret,
            "PRODUCTION_CREDENTIALS_ROTATED": "false",
            "ALLOW_MANUAL_ANALYSIS_IN_DEVELOPMENT": "false",
            "RAZORPAY_MODE": "live",
            "ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT": "false",
            "RAZORPAY_WEBHOOK_SECRET": generated_webhook,
            "RAZORPAY_KEY_ID": str(imported.get("razorpay_key_id") or ""),
            "RAZORPAY_KEY_SECRET": str(imported.get("razorpay_key_secret") or ""),
            "LEGAL_OPERATOR_NAME": "",
            "LEGAL_OPERATOR_ADDRESS": "",
            "LEGAL_CONTACT_EMAIL": "",
            "PRIVACY_CONTACT_EMAIL": "",
            "CUSTOMER_CARE_EMAIL": "",
            "CUSTOMER_CARE_PHONE": "",
            "GRIEVANCE_OFFICER_NAME": "",
            "GRIEVANCE_EMAIL": "",
            "GRIEVANCE_PHONE": "",
            "LEGAL_GSTIN": "",
            "LEGAL_PAN": "",
            "EMAIL_VERIFICATION_REQUIRED": "true",
            "APP_PUBLIC_URL": "",
            "FRONTEND_URL": "",
            "RESEND_API_KEY": "",
            "EMAIL_FROM": "",
            "SMTP_HOST": "",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "SMTP_FROM_EMAIL": "",
            "SMTP_FROM_NAME": "ClipKaro AI",
            "SMTP_STARTTLS": "true",
            "SMTP_USE_SSL": "false",
            "GROQ_RANKING_ENABLED": "true",
            "GROQ_RANKING_MODEL": "openai/gpt-oss-120b",
            "GROQ_RANKING_FALLBACK_MODEL": "openai/gpt-oss-20b",
            **{f"GROQ_API_KEY_{i}": key for i, key in enumerate(groq[:5], start=1)},
            "ASR_MODE": "api",
            "ASR_PRIMARY_PROVIDER": "groq",
            "ASR_FALLBACK_PROVIDER": "cloudflare",
            "GROQ_ASR_MODEL": "whisper-large-v3",
            "CLOUDFLARE_ACCOUNT_ID": "",
            "CLOUDFLARE_API_TOKEN": "",
            "CLOUDFLARE_ASR_MODEL": "@cf/openai/whisper-large-v3-turbo",
            "WHISPER_MODEL": "medium",
            "WHISPER_SECONDARY_MODEL": "small",
            "REQUIRE_ASR_CONSENSUS": "false",
            "ALIGNMENT_BACKEND": "native",
            "REQUIRE_FORCED_ALIGNMENT": "false",
            "UPLOAD_SCAN_REQUIRED": "true",
        }

    domain = ask("Public domain (for example clipkaro.example)")
    acme = ask("ACME/TLS email")
    resend_key = ask("Resend API key (recommended; blank to use SMTP)", secret=True, required=False)
    email_from = ask("Transactional From address (for example ClipKaro AI <verify@mail.yourdomain>)", required=bool(resend_key))
    smtp_host = ask("SMTP host (optional when Resend is configured)", required=not bool(resend_key))
    smtp_port = ask("SMTP port", default="587")
    smtp_user = ask("SMTP username", required=False)
    smtp_password = ask("SMTP password", secret=True, required=bool(smtp_user))
    smtp_from = ask("SMTP From email", required=bool(smtp_host) and not bool(email_from))

    razorpay_id = ask("Razorpay LIVE key ID", default=str(imported.get("razorpay_key_id") or ""))
    razorpay_secret = ask("Razorpay LIVE key secret", secret=True)
    webhook_secret = generated_webhook
    print("Generated a new Razorpay webhook secret. Its value will be written only to the output env file.")

    cloudflare_account_id = ask("Cloudflare account ID for ASR fallback")
    cloudflare_api_token = ask("Cloudflare API token for ASR fallback", secret=True)

    groq_imported = list(imported.get("groq") or [])
    groq_values: list[str] = []
    for idx in range(1, 6):
        default = groq_imported[idx - 1] if idx <= len(groq_imported) else ""
        value = ask(f"Groq API key {idx}", secret=True, default=default, required=idx == 1)
        if value:
            groq_values.append(value)

    env = {
        "DOMAIN": domain,
        "ACME_EMAIL": acme,
        "SECRET_KEY": generated_secret,
        "PRODUCTION_CREDENTIALS_ROTATED": ask(
            "Have Razorpay/Groq credentials been rotated after any plaintext exposure? (true/false)",
            default="false",
        ).lower(),
        "ALLOW_MANUAL_ANALYSIS_IN_DEVELOPMENT": "false",
        "RAZORPAY_MODE": "live",
        "ALLOW_LIVE_RAZORPAY_IN_DEVELOPMENT": "false",
        "RAZORPAY_WEBHOOK_SECRET": webhook_secret,
        "RAZORPAY_KEY_ID": razorpay_id,
        "RAZORPAY_KEY_SECRET": razorpay_secret,
        "LEGAL_OPERATOR_NAME": ask("Legal entity/proprietor name"),
        "LEGAL_OPERATOR_ADDRESS": ask("Principal geographic address"),
        "LEGAL_CONTACT_EMAIL": ask("Legal contact email"),
        "PRIVACY_CONTACT_EMAIL": ask("Privacy contact email"),
        "CUSTOMER_CARE_EMAIL": ask("Customer-care email"),
        "CUSTOMER_CARE_PHONE": ask("Customer-care phone"),
        "GRIEVANCE_OFFICER_NAME": ask("Grievance officer name"),
        "GRIEVANCE_EMAIL": ask("Grievance email"),
        "GRIEVANCE_PHONE": ask("Grievance phone"),
        "LEGAL_GSTIN": ask("GSTIN (blank if not applicable)", required=False),
        "LEGAL_PAN": ask("PAN (blank if not applicable)", required=False),
        "EMAIL_VERIFICATION_REQUIRED": "true",
        "APP_PUBLIC_URL": f"https://{domain}",
        "FRONTEND_URL": f"https://{domain}",
        "RESEND_API_KEY": resend_key,
        "EMAIL_FROM": email_from,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port,
        "SMTP_USERNAME": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_FROM_EMAIL": smtp_from,
        "SMTP_FROM_NAME": "ClipKaro AI",
        "SMTP_STARTTLS": "true",
        "SMTP_USE_SSL": "false",
        "GROQ_RANKING_ENABLED": "true",
        "GROQ_RANKING_MODEL": "openai/gpt-oss-120b",
        "GROQ_RANKING_FALLBACK_MODEL": "openai/gpt-oss-20b",
        **{f"GROQ_API_KEY_{i}": key for i, key in enumerate(groq_values, start=1)},
        "ASR_MODE": "api",
        "ASR_PRIMARY_PROVIDER": "groq",
        "ASR_FALLBACK_PROVIDER": "cloudflare",
        "GROQ_ASR_MODEL": "whisper-large-v3",
        "CLOUDFLARE_ACCOUNT_ID": cloudflare_account_id,
        "CLOUDFLARE_API_TOKEN": cloudflare_api_token,
        "CLOUDFLARE_ASR_MODEL": "@cf/openai/whisper-large-v3-turbo",
        "WHISPER_MODEL": "medium",
        "WHISPER_SECONDARY_MODEL": "small",
        "REQUIRE_ASR_CONSENSUS": "false",
        "ALIGNMENT_BACKEND": "native",
        "REQUIRE_FORCED_ALIGNMENT": "false",
        "UPLOAD_SCAN_REQUIRED": "true",
    }
    return env


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".clipkaro-env-", dir=str(path.parent))
    os.close(fd)
    temp_path = Path(temp)
    try:
        lines = [
            "# ClipKaro private production VPS environment.",
            "# NEVER commit, paste into issues/PRs, or serve this file over HTTP.",
            "# chmod 600 is applied by this script.",
            "",
        ]
        for key, value in values.items():
            escaped = value.replace("\\", "\\\\").replace("\n", "\\n")
            lines.append(f"{key}={escaped}")
        temp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create ClipKaro's private production VPS .env without printing secrets.")
    parser.add_argument("--output", default=".env")
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--draft", action="store_true", help="Write a fail-closed draft with missing transactional-email/legal values.")
    args = parser.parse_args()
    imported = parse_credential_file(args.credential_file)
    values = build_env(imported, draft=args.draft)
    write_env(Path(args.output), values)
    print(f"Wrote private env to {args.output}. Secret values were not printed.")
    if args.draft:
        print("Draft remains paid-launch BLOCKED until transactional-email/legal fields and rotated provider credentials are supplied.")
    else:
        print("Run: python scripts/check-production-env.py --env-file " + args.output + " --require-ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

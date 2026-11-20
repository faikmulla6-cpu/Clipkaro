from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CartoonCredentialError(RuntimeError):
    pass


def _cipher() -> Fernet:
    settings = get_settings()
    secret = settings.post_karo_encryption_key.strip()
    if not secret:
        if settings.app_env.strip().lower() == "production":
            raise CartoonCredentialError("Secure AI provider storage is temporarily unavailable.")
        secret = settings.secret_key
    material = hashlib.sha256(
        ("clipkaro:cartoon-provider-credentials:v1:" + secret).encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_provider_key(value: str) -> str:
    return "v1:" + _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_provider_key(value: str) -> str:
    ciphertext = str(value or "")
    if not ciphertext.startswith("v1:"):
        raise CartoonCredentialError("Reconnect your AI provider securely.")
    try:
        return _cipher().decrypt(ciphertext[3:].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise CartoonCredentialError("Reconnect your AI provider securely.") from exc


def mask_provider_key(value: str) -> str:
    secret = str(value or "")
    if len(secret) < 12:
        return "••••••••"
    return f"{secret[:7]}••••••••{secret[-4:]}"


def fingerprint_provider_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]

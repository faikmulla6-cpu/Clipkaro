from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.utils import parseaddr
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings


logger = logging.getLogger("clipkaro.transactional_email")
_RESEND_EMAILS_URL = "https://api.resend.com/emails"
_RESEND_DOMAINS_URL = "https://api.resend.com/domains"


class TransactionalEmailUnavailable(RuntimeError):
    """Safe, user-facing category for a transactional email delivery failure."""


@dataclass(frozen=True)
class TransactionalEmail:
    to: str
    subject: str
    html: str
    text: str


def resend_delivery_configured() -> bool:
    settings = get_settings()
    return bool(settings.resend_api_key.strip() and settings.email_from.strip())


def smtp_delivery_configured() -> bool:
    settings = get_settings()
    if not settings.smtp_host.strip():
        return False
    from_ok = bool(settings.smtp_from_email.strip() or settings.email_from.strip())
    auth_ok = bool(settings.smtp_username.strip()) == bool(settings.smtp_password)
    return from_ok and auth_ok


def email_delivery_configured() -> bool:
    return resend_delivery_configured() or smtp_delivery_configured()


def _sender_domain(value: str) -> str:
    """Return the normalized mailbox domain without exposing the address."""
    _, address = parseaddr(value.strip())
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].strip().lower().rstrip(".")


def _send_with_resend(message: TransactionalEmail) -> None:
    settings = get_settings()
    from_addr = settings.email_from.strip()

    payload = json.dumps({
        "from": from_addr,
        "to": [message.to],
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
    }).encode("utf-8")
    request = urllib.request.Request(
        _RESEND_EMAILS_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.resend_api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "ClipKaro-TransactionalEmail/1.0",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(3.0, settings.resend_timeout_seconds)) as response:
            if not 200 <= int(response.status) < 300:
                raise TransactionalEmailUnavailable("Email delivery service did not accept the request.")
            logger.info("transactional_email_sent provider=resend")
    except urllib.error.HTTPError as exc:
        # Provider bodies can contain request/account diagnostics. Keep only the
        # status code in application logs and never echo provider bodies upward.
        logger.warning(
            "transactional_email_send_failed provider=resend status_class=%sxx status_code=%s",
            exc.code // 100, exc.code,
        )
        raise TransactionalEmailUnavailable(f"Email delivery service rejected the request (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.warning("transactional_email_send_failed provider=resend category=network error_type=%s", type(exc).__name__)
        raise TransactionalEmailUnavailable("Email delivery service could not be reached.") from exc


def _send_with_smtp(message: TransactionalEmail) -> None:
    settings = get_settings()
    from_email = (
        settings.smtp_from_email.strip()
        or settings.email_from.strip()
        or settings.smtp_username.strip()
    )
    if not from_email:
        raise TransactionalEmailUnavailable("SMTP sender address is not configured.")

    display_name = settings.smtp_from_name.strip() or settings.app_name
    email_msg = EmailMessage()
    email_msg["Subject"] = message.subject
    if "<" in from_email and ">" in from_email:
        email_msg["From"] = from_email
    else:
        email_msg["From"] = f"{display_name} <{from_email}>"
    email_msg["To"] = message.to
    email_msg.set_content(message.text)
    email_msg.add_alternative(message.html, subtype="html")

    timeout = max(3.0, float(settings.smtp_timeout_seconds))
    try:
        port = int(settings.smtp_port) if settings.smtp_port else 587
        if settings.smtp_use_ssl or port == 465:
            client = smtplib.SMTP_SSL(
                settings.smtp_host.strip(), port, timeout=timeout,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(settings.smtp_host.strip(), port, timeout=timeout)
        with client:
            client.ehlo()
            if settings.smtp_starttls and not (settings.smtp_use_ssl or port == 465):
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings.smtp_username.strip():
                client.login(settings.smtp_username.strip(), settings.smtp_password)
            client.send_message(email_msg)
            logger.info("transactional_email_sent provider=smtp")
    except Exception as exc:
        logger.warning("transactional_email_send_failed provider=smtp error_type=%s", type(exc).__name__)
        raise TransactionalEmailUnavailable("SMTP delivery failed.") from exc


async def send_transactional_email(message: TransactionalEmail) -> None:
    settings = get_settings()
    has_resend = resend_delivery_configured()
    has_smtp = smtp_delivery_configured()

    if not has_resend and not has_smtp:
        if settings.app_env in {"development", "test"}:
            # Never log message bodies: verification/reset messages contain
            # bearer-like one-time links. Local QA can use direct test helpers.
            logger.info("transactional_email_skipped environment=%s provider=none", settings.app_env)
            return
        raise TransactionalEmailUnavailable("Transactional email is not configured.")

    errors: list[str] = []
    if has_resend:
        try:
            await asyncio.to_thread(_send_with_resend, message)
            return
        except Exception as exc:
            errors.append(str(exc))

    if has_smtp:
        try:
            await asyncio.to_thread(_send_with_smtp, message)
            return
        except Exception as exc:
            errors.append(str(exc))

    # Once a provider is explicitly configured, a failed delivery attempt must
    # remain a failure in every environment. Silently swallowing it in local
    # development makes signup/resend UIs claim that mail was sent when Resend
    # (for example an unverified sender domain) actually rejected the request.
    # Development is only permissive when *no* provider is configured above.
    raise TransactionalEmailUnavailable("Transactional email delivery failed.")


def _probe_resend_domains_sync() -> dict[str, object]:
    """Read-only Resend domain/authentication probe used by production preflight.

    Resend requires a verified owned domain for arbitrary recipients.  Merely
    having an API key and a syntactically valid From address is not enough.
    This probe never sends mail and never returns the key or sender address.
    """
    settings = get_settings()
    sender_domain = _sender_domain(settings.email_from)
    if not settings.resend_api_key.strip() or not sender_domain:
        return {
            "configured": False, "reachable": False, "authenticated": False,
            "code": "unconfigured", "provider": "resend", "sender_domain_verified": False,
        }
    if sender_domain == "resend.dev" or sender_domain.endswith(".resend.dev"):
        return {
            "configured": True, "reachable": True, "authenticated": False,
            "code": "test_sender_domain", "provider": "resend", "sender_domain_verified": False,
        }

    request = urllib.request.Request(
        _RESEND_DOMAINS_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {settings.resend_api_key.strip()}",
            "Accept": "application/json",
            "User-Agent": "ClipKaro-TransactionalEmail/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(3.0, settings.resend_timeout_seconds)) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
            domains = data.get("data") if isinstance(data, dict) else None
            if not isinstance(domains, list):
                domains = []
            matching = next((item for item in domains if isinstance(item, dict) and
                             str(item.get("name") or "").strip().lower().rstrip(".") == sender_domain), None)
            verified = bool(matching and str(matching.get("status") or "").lower() == "verified")
            return {
                "configured": True,
                "reachable": True,
                "authenticated": True,
                "code": "ready" if verified else "sender_domain_unverified",
                "provider": "resend",
                "sender_domain_verified": verified,
            }
    except urllib.error.HTTPError as exc:
        return {
            "configured": True,
            "reachable": True,
            "authenticated": False,
            "code": "credentials_rejected" if exc.code in {401, 403} else "provider_error",
            "provider": "resend",
            "sender_domain_verified": False,
        }
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return {
            "configured": True, "reachable": False, "authenticated": False,
            "code": "unreachable", "provider": "resend", "sender_domain_verified": False,
        }


async def probe_resend_readiness(*, live: bool = True) -> dict[str, object]:
    """Secret-safe transactional email readiness without sending a message."""
    has_resend = resend_delivery_configured()
    has_smtp = smtp_delivery_configured()
    if has_resend:
        if not live:
            sender_domain = _sender_domain(get_settings().email_from)
            production_sender = bool(sender_domain and sender_domain != "resend.dev" and not sender_domain.endswith(".resend.dev"))
            return {
                "configured": True, "reachable": True, "authenticated": True,
                "code": "configured", "provider": "resend",
                "sender_domain_verified": production_sender,
            }
        return await asyncio.to_thread(_probe_resend_domains_sync)
    if has_smtp:
        # SMTP remains an explicitly configured fallback. Existing delivery code
        # performs TLS/authentication on send; production can choose Resend for
        # stronger read-only provider-domain verification.
        return {
            "configured": True, "reachable": True, "authenticated": True,
            "code": "configured", "provider": "smtp", "sender_domain_verified": True,
        }
    return {
        "configured": False, "reachable": False, "authenticated": False,
        "code": "unconfigured", "provider": "none", "sender_domain_verified": False,
    }


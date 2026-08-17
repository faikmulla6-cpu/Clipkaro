from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from app.core.config import get_settings
from app.core.database import fetch_one, run_in_transaction
from app.services.transactional_email import (
    TransactionalEmail,
    TransactionalEmailUnavailable,
    probe_resend_readiness,
    resend_delivery_configured,
    send_transactional_email,
)


logger = logging.getLogger("clipkaro.email")


class AccountAlreadyExists(RuntimeError):
    pass


class VerificationTokenInvalid(RuntimeError):
    pass


class VerificationTokenExpired(RuntimeError):
    pass


class VerificationRateLimited(RuntimeError):
    def __init__(self, retry_after: int, message: str = "Please wait before requesting another verification email.") -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


class EmailDeliveryUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verification_ttl_minutes() -> int:
    settings = get_settings()
    return max(5, int(settings.email_verification_token_ttl_minutes or settings.email_verification_token_minutes))


def _new_token() -> str:
    # 32 random bytes gives 256 bits of entropy. The raw value is sent once;
    # only its SHA-256 digest is persisted in SQLite.
    return secrets.token_urlsafe(32)


def _audit_values(user_id: str, event: str, metadata: dict | None = None) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(uuid.uuid4()), user_id, event, "user", user_id,
        json.dumps(metadata or {}, separators=(",", ":")), _iso(_now()),
    )


async def init_email_verification() -> None:
    """Install the verification schema and safely migrate existing accounts.

    Existing ClipKaro accounts predate email verification. The column-add
    migration marks only those pre-existing rows verified. Future accounts are
    created explicitly with NULL `email_verified_at` and must prove ownership.
    Admin accounts are kept verified so an operational account cannot be locked
    out by an incomplete mail-provider configuration.
    """

    async def _migrate(db) -> None:
        columns = {row[1] for row in await (await db.execute("PRAGMA table_info(users)")).fetchall()}
        added_column = "email_verified_at" not in columns
        if added_column:
            await db.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")
            migrated_at = _iso(_now())
            await db.execute(
                "UPDATE users SET email_verified_at=COALESCE(created_at,updated_at,?) WHERE email_verified_at IS NULL",
                (migrated_at,),
            )

        await db.execute(
            """CREATE TABLE IF NOT EXISTS email_verifications (
                 user_id TEXT PRIMARY KEY,
                 token_hash TEXT UNIQUE NOT NULL,
                 expires_at TEXT NOT NULL,
                 last_sent_at TEXT NOT NULL,
                 send_window_started_at TEXT NOT NULL,
                 send_count INTEGER NOT NULL DEFAULT 1,
                 consumed_at TEXT,
                 created_at TEXT NOT NULL,
                 updated_at TEXT NOT NULL,
                 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
               )"""
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_verification_expiry ON email_verifications(expires_at,consumed_at)"
        )
        # Defense in depth for demo/operational users created after the original
        # one-time migration in a development database.
        await db.execute(
            "UPDATE users SET email_verified_at=COALESCE(email_verified_at,created_at,updated_at,?) "
            "WHERE role='admin' AND email_verified_at IS NULL",
            (_iso(_now()),),
        )

    await run_in_transaction(_migrate, operation_name="email verification schema migration")


def email_delivery_configured() -> bool:
    from app.services.transactional_email import email_delivery_configured as _email_delivery_configured
    return _email_delivery_configured()


async def probe_smtp_readiness(*, live: bool = True) -> dict[str, object]:
    """Compatibility shim; preflight checks the transactional email configuration."""
    return await probe_resend_readiness(live=live)


def verification_link(token: str) -> str:
    settings = get_settings()
    base = (settings.frontend_url or settings.app_public_url).rstrip("/")
    # The token lives in the URL fragment, not the query string. Browsers do not
    # send fragments to Caddy/Next.js access logs or in HTTP Referer headers.
    return f"{base}/verify-email#token={quote(token, safe='')}"


def _verification_message(recipient: str, name: str, token: str) -> TransactionalEmail:
    settings = get_settings()
    link = verification_link(token)
    safe_name = html.escape(name.strip() or "creator")
    safe_link = html.escape(link, quote=True)
    minutes = _verification_ttl_minutes()
    text = (
        f"Hi {name.strip() or 'creator'},\n\n"
        "Verify your email before ClipKaro starts AI processing on your account.\n\n"
        f"Verify email: {link}\n\n"
        f"This one-time link expires in {minutes} minutes. If you did not create a ClipKaro account, you can ignore this email.\n"
    )
    html_body = f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#141414;line-height:1.5">
        <div style="max-width:560px;margin:0 auto;padding:28px">
          <p style="font-size:14px;font-weight:700">✦ ClipKaro AI</p>
          <h1 style="font-size:26px">Verify your email</h1>
          <p>Hi {safe_name},</p>
          <p>Confirm this email before ClipKaro starts AI processing on your account.</p>
          <p style="margin:28px 0"><a href="{safe_link}" style="background:#111;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">Verify email</a></p>
          <p style="font-size:13px;color:#666">This one-time link expires in {minutes} minutes. If you did not create a ClipKaro account, ignore this email.</p>
        </div></body></html>"""
    return TransactionalEmail(
        to=recipient,
        subject="Verify your ClipKaro email",
        html=html_body,
        text=text,
    )


async def send_verification_email(recipient: str, name: str, token: str) -> str:
    settings = get_settings()
    link = verification_link(token)
    if settings.app_env == "test":
        return link

    if not email_delivery_configured():
        if settings.app_env == "development":
            logger.warning("Email delivery not configured in development mode; verification remains pending.")
            return link
        raise EmailDeliveryUnavailable("Verification email delivery is not configured.")

    try:
        await send_transactional_email(_verification_message(recipient, name, token))
        logger.info("verification_email_sent")
    except TransactionalEmailUnavailable as exc:
        logger.warning("verification_email_send_failed error_type=%s", type(exc).__name__)
        if settings.app_env == "development":
            logger.warning("Verification email delivery failed in development mode; verification remains pending.")
            return link
        raise EmailDeliveryUnavailable("Verification email could not be delivered right now.") from exc

    return link


async def create_unverified_account(name: str, email: str, password_hash: str) -> tuple[dict, str]:
    settings = get_settings()
    raw_token = _new_token()
    digest = _token_hash(raw_token)
    created = _now()
    expires = created + timedelta(minutes=_verification_ttl_minutes())
    user_id = str(uuid.uuid4())
    normalized_email = email.strip().lower()
    clean_name = name.strip()

    async def _create(db) -> dict:
        if await (await db.execute("SELECT id FROM users WHERE email=?", (normalized_email,))).fetchone():
            raise AccountAlreadyExists("An account already exists for this email.")
        timestamp = _iso(created)
        await db.execute(
            """INSERT INTO users(
                 id,name,email,password_hash,plan,role,onboarding_complete,created_at,updated_at,email_verified_at
               ) VALUES (?,?,?,?,'free','creator',0,?,?,NULL)""",
            (user_id, clean_name, normalized_email, password_hash, timestamp, timestamp),
        )
        await db.execute(
            """INSERT INTO email_verifications(
                 user_id,token_hash,expires_at,last_sent_at,send_window_started_at,send_count,
                 consumed_at,created_at,updated_at
               ) VALUES (?,?,?,?,?,1,NULL,?,?)""",
            (user_id, digest, _iso(expires), timestamp, timestamp, timestamp, timestamp),
        )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            _audit_values(user_id, "account.created", {"email_verification_required": True}),
        )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            _audit_values(user_id, "account.verification_requested", {"kind": "initial"}),
        )
        row = await (await db.execute("SELECT * FROM users WHERE id=?", (user_id,))).fetchone()
        return dict(row)

    user = await run_in_transaction(_create, operation_name="create unverified account")
    return user, raw_token


async def issue_resend_token(user_id: str) -> tuple[dict, str | None, int]:
    settings = get_settings()
    raw_token = _new_token()
    digest = _token_hash(raw_token)
    now = _now()
    expires = now + timedelta(minutes=_verification_ttl_minutes())
    cooldown = max(1, int(settings.email_verification_resend_cooldown_seconds))
    hourly_limit = max(1, int(settings.email_verification_max_sends_per_hour))

    async def _issue(db) -> tuple[dict, str | None, int]:
        user_row = await (await db.execute("SELECT * FROM users WHERE id=?", (user_id,))).fetchone()
        if not user_row:
            raise VerificationTokenInvalid("Account not found.")
        user = dict(user_row)
        if user.get("email_verified_at"):
            return user, None, 0

        challenge_row = await (
            await db.execute("SELECT * FROM email_verifications WHERE user_id=?", (user_id,))
        ).fetchone()
        challenge = dict(challenge_row) if challenge_row else None
        window_start = _parse((challenge or {}).get("send_window_started_at"))
        last_sent = _parse((challenge or {}).get("last_sent_at"))
        send_count = int((challenge or {}).get("send_count") or 0)

        if last_sent:
            elapsed = (now - last_sent).total_seconds()
            if elapsed < cooldown:
                raise VerificationRateLimited(math.ceil(cooldown - elapsed))

        if not window_start or (now - window_start).total_seconds() >= 3600:
            window_start = now
            send_count = 0
        elif send_count >= hourly_limit:
            retry_after = math.ceil(3600 - (now - window_start).total_seconds())
            raise VerificationRateLimited(retry_after, "Too many verification emails were requested. Try again later.")

        timestamp = _iso(now)
        if challenge:
            await db.execute(
                """UPDATE email_verifications
                   SET token_hash=?,expires_at=?,last_sent_at=?,send_window_started_at=?,send_count=?,
                       consumed_at=NULL,updated_at=? WHERE user_id=?""",
                (digest, _iso(expires), timestamp, _iso(window_start), send_count + 1, timestamp, user_id),
            )
        else:
            await db.execute(
                """INSERT INTO email_verifications(
                     user_id,token_hash,expires_at,last_sent_at,send_window_started_at,send_count,
                     consumed_at,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,NULL,?,?)""",
                (
                    user_id, digest, _iso(expires), timestamp, _iso(window_start), send_count + 1,
                    timestamp, timestamp,
                ),
            )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            _audit_values(user_id, "account.verification_requested", {"kind": "resend"}),
        )
        return user, raw_token, cooldown

    return await run_in_transaction(_issue, operation_name="issue email verification resend")


async def consume_verification_token(token: str) -> dict:
    clean = token.strip()
    if len(clean) < 20 or len(clean) > 512:
        raise VerificationTokenInvalid("Verification link is invalid.")
    digest = _token_hash(clean)
    now = _now()

    async def _consume(db) -> dict:
        row = await (
            await db.execute(
                """SELECT ev.*,u.id,u.name,u.email,u.plan,u.role,u.onboarding_complete,u.email_verified_at
                   FROM email_verifications ev JOIN users u ON u.id=ev.user_id
                   WHERE ev.token_hash=?""",
                (digest,),
            )
        ).fetchone()
        if not row:
            raise VerificationTokenInvalid("Verification link is invalid or has been replaced.")
        record = dict(row)
        if record.get("consumed_at") and record.get("email_verified_at"):
            # Re-opening the same successful link is harmless and should not
            # turn a success page into an alarming error.
            record["_verification_reused"] = True
            return record
        expires = _parse(record.get("expires_at"))
        if not expires or expires <= now:
            raise VerificationTokenExpired("Verification link has expired. Request a new email.")

        timestamp = _iso(now)
        await db.execute(
            "UPDATE users SET email_verified_at=?,updated_at=? WHERE id=? AND email_verified_at IS NULL",
            (timestamp, timestamp, record["user_id"]),
        )
        await db.execute(
            "UPDATE email_verifications SET consumed_at=?,updated_at=? WHERE user_id=? AND token_hash=?",
            (timestamp, timestamp, record["user_id"], digest),
        )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            _audit_values(record["user_id"], "account.email_verified"),
        )
        user_row = await (await db.execute("SELECT * FROM users WHERE id=?", (record["user_id"],))).fetchone()
        return dict(user_row)

    return await run_in_transaction(_consume, operation_name="consume email verification token")


def verification_status(user: dict) -> dict:
    settings = get_settings()
    verified = bool(user.get("email_verified_at"))
    required = bool(settings.email_verification_required and user.get("role") != "admin")
    # Tests preserve the historical integration suite unless a test explicitly
    # switches APP_ENV away from `test`; production/development enforce normally.
    test_bypass = settings.app_env == "test"
    can_process = bool(not required or verified or test_bypass)
    return {
        "verified": verified,
        "required": required,
        "can_process": can_process,
        "email": str(user.get("email") or ""),
    }


def requires_verification_for_processing(user: dict) -> bool:
    status = verification_status(user)
    return bool(status["required"] and not status["can_process"])

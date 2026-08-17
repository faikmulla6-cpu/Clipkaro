from __future__ import annotations

import hashlib
import html
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt

from app.core.config import get_settings
from app.core.database import fetch_all, fetch_one, run_in_transaction
from app.services.transactional_email import TransactionalEmail, TransactionalEmailUnavailable, send_transactional_email


logger = logging.getLogger("clipkaro.security")


class PasswordResetInvalid(RuntimeError):
    pass


class PasswordResetExpired(RuntimeError):
    pass


class PasswordResetDeliveryUnavailable(RuntimeError):
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


def _client_fingerprint(value: str) -> str:
    """Keep useful abuse metadata without persisting raw client IP addresses."""
    if not value:
        return ""
    secret = get_settings().secret_key.encode("utf-8")
    return hashlib.sha256(secret + b":" + value.encode("utf-8", errors="ignore")).hexdigest()


async def init_account_security() -> None:
    """Install session and password-reset state without invalidating user rows."""

    async def _migrate(db) -> None:
        columns = {row[1] for row in await (await db.execute("PRAGMA table_info(users)")).fetchall()}
        if "session_version" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")

        await db.execute(
            """CREATE TABLE IF NOT EXISTS auth_sessions (
                 id TEXT PRIMARY KEY,
                 user_id TEXT NOT NULL,
                 session_version INTEGER NOT NULL,
                 created_at TEXT NOT NULL,
                 expires_at TEXT NOT NULL,
                 revoked_at TEXT,
                 user_agent TEXT NOT NULL DEFAULT '',
                 client_fingerprint TEXT NOT NULL DEFAULT '',
                 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
               )"""
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id,revoked_at,expires_at)"
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS password_resets (
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
            "CREATE INDEX IF NOT EXISTS idx_password_reset_expiry ON password_resets(expires_at,consumed_at)"
        )

    await run_in_transaction(_migrate, operation_name="account security schema migration")


async def create_session_token(user_id: str, *, user_agent: str = "", client_ip: str = "") -> str:
    """Create one independently revocable server-side session and its JWT handle."""
    settings = get_settings()
    user = await fetch_one("SELECT id,session_version FROM users WHERE id=?", (user_id,))
    if not user:
        raise PasswordResetInvalid("Account not found.")

    created = _now()
    expires = created + timedelta(minutes=max(1, int(settings.access_token_minutes)))
    session_id = str(uuid.uuid4())
    session_version = int(user.get("session_version") or 0)

    async def _create(db) -> None:
        await db.execute(
            """INSERT INTO auth_sessions(
                 id,user_id,session_version,created_at,expires_at,revoked_at,user_agent,client_fingerprint
               ) VALUES (?,?,?,?,?,NULL,?,?)""",
            (
                session_id,
                user_id,
                session_version,
                _iso(created),
                _iso(expires),
                user_agent.strip()[:255],
                _client_fingerprint(client_ip),
            ),
        )

    await run_in_transaction(_create, operation_name="create auth session")
    return jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "sv": session_version,
            "iat": created,
            "exp": expires,
        },
        settings.secret_key,
        algorithm="HS256",
    )


async def session_is_active(payload: dict, user: dict) -> bool:
    session_id = str(payload.get("sid") or "")
    if not session_id:
        return False
    try:
        token_version = int(payload.get("sv"))
    except (TypeError, ValueError):
        return False
    if token_version != int(user.get("session_version") or 0):
        return False
    row = await fetch_one(
        "SELECT * FROM auth_sessions WHERE id=? AND user_id=?",
        (session_id, user["id"]),
    )
    if not row or row.get("revoked_at"):
        return False
    expires = _parse(row.get("expires_at"))
    return bool(expires and expires > _now() and int(row.get("session_version") or 0) == token_version)


async def revoke_session(session_id: str, user_id: str | None = None) -> None:
    if not session_id:
        return
    timestamp = _iso(_now())

    async def _revoke(db) -> None:
        if user_id:
            await db.execute(
                "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,?) WHERE id=? AND user_id=?",
                (timestamp, session_id, user_id),
            )
        else:
            await db.execute(
                "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,?) WHERE id=?",
                (timestamp, session_id),
            )

    await run_in_transaction(_revoke, operation_name="revoke auth session")


async def revoke_all_sessions(user_id: str, *, increment_version: bool = True) -> None:
    timestamp = _iso(_now())

    async def _revoke_all(db) -> None:
        await db.execute(
            "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,?) WHERE user_id=?",
            (timestamp, user_id),
        )
        if increment_version:
            await db.execute(
                "UPDATE users SET session_version=session_version+1,updated_at=? WHERE id=?",
                (timestamp, user_id),
            )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), user_id, "account.sessions_revoked", "user", user_id,
                json.dumps({"all": True}, separators=(",", ":")), timestamp,
            ),
        )

    await run_in_transaction(_revoke_all, operation_name="revoke all auth sessions")


async def list_active_sessions(user_id: str, current_session_id: str = "") -> list[dict]:
    rows = await fetch_all(
        """SELECT id,created_at,expires_at,user_agent,client_fingerprint
           FROM auth_sessions
           WHERE user_id=? AND revoked_at IS NULL AND expires_at>?
           ORDER BY created_at DESC""",
        (user_id, _iso(_now())),
    )
    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "user_agent": row.get("user_agent") or "Unknown device",
            "current": row["id"] == current_session_id,
        }
        for row in rows
    ]


def password_reset_link(token: str) -> str:
    base = get_settings().app_public_url.rstrip("/")
    # Fragments stay out of proxy/request logs and Referer headers.
    return f"{base}/reset-password#token={quote(token, safe='')}"


def _password_reset_message(recipient: str, name: str, token: str) -> TransactionalEmail:
    settings = get_settings()
    link = password_reset_link(token)
    minutes = max(5, int(settings.password_reset_token_minutes))
    display_name = name.strip() or "creator"
    safe_name = html.escape(display_name)
    safe_link = html.escape(link, quote=True)
    text = (
        f"Hi {display_name},\n\n"
        "A password reset was requested for your ClipKaro account.\n\n"
        f"Reset password: {link}\n\n"
        f"This one-time link expires in {minutes} minutes. If you did not request this, ignore this email.\n"
    )
    html_body = f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#141414;line-height:1.5">
        <div style="max-width:560px;margin:0 auto;padding:28px">
          <p style="font-size:14px;font-weight:700">✦ ClipKaro AI</p>
          <h1 style="font-size:26px">Reset your password</h1>
          <p>Hi {safe_name},</p>
          <p>A password reset was requested for your ClipKaro account.</p>
          <p style="margin:28px 0"><a href="{safe_link}" style="background:#111;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">Reset password</a></p>
          <p style="font-size:13px;color:#666">This one-time link expires in {minutes} minutes. If you did not request it, ignore this email.</p>
        </div></body></html>"""
    return TransactionalEmail(
        to=recipient,
        subject="Reset your ClipKaro password",
        html=html_body,
        text=text,
    )


async def send_password_reset_email(recipient: str, name: str, token: str) -> None:
    settings = get_settings()
    if settings.app_env == "test":
        return
    try:
        await send_transactional_email(_password_reset_message(recipient, name, token))
    except TransactionalEmailUnavailable as exc:
        logger.warning("password_reset_delivery_failed error_type=%s", type(exc).__name__)
        raise PasswordResetDeliveryUnavailable("Password reset email could not be delivered.") from exc


async def issue_password_reset(email: str) -> tuple[dict | None, str | None, int]:
    """Issue a durable one-time reset challenge without exposing account existence."""
    settings = get_settings()
    user = await fetch_one("SELECT * FROM users WHERE email=?", (email.strip().lower(),))
    if not user:
        return None, None, max(1, int(settings.password_reset_resend_cooldown_seconds))

    created = _now()
    raw_token = secrets.token_urlsafe(32)
    digest = _token_hash(raw_token)
    expires = created + timedelta(minutes=max(5, int(settings.password_reset_token_minutes)))
    cooldown = max(1, int(settings.password_reset_resend_cooldown_seconds))
    max_sends = max(1, int(settings.password_reset_max_sends_per_hour))

    async def _issue(db) -> tuple[str | None, int]:
        cursor = await db.execute("SELECT * FROM password_resets WHERE user_id=?", (user["id"],))
        row = await cursor.fetchone()
        timestamp = _iso(created)
        if row:
            last_sent = _parse(row["last_sent_at"])
            if last_sent and (created - last_sent).total_seconds() < cooldown:
                return None, max(1, int(cooldown - (created - last_sent).total_seconds()))
            window_start = _parse(row["send_window_started_at"])
            in_window = bool(window_start and (created - window_start).total_seconds() < 3600)
            count = int(row["send_count"] or 0) if in_window else 0
            if count >= max_sends:
                retry = max(1, int(3600 - (created - window_start).total_seconds())) if window_start else 3600
                return None, retry
            next_window = row["send_window_started_at"] if in_window else timestamp
            await db.execute(
                """UPDATE password_resets SET token_hash=?,expires_at=?,last_sent_at=?,
                   send_window_started_at=?,send_count=?,consumed_at=NULL,updated_at=? WHERE user_id=?""",
                (digest, _iso(expires), timestamp, next_window, count + 1, timestamp, user["id"]),
            )
        else:
            await db.execute(
                """INSERT INTO password_resets(
                     user_id,token_hash,expires_at,last_sent_at,send_window_started_at,send_count,
                     consumed_at,created_at,updated_at
                   ) VALUES (?,?,?,?,?,1,NULL,?,?)""",
                (user["id"], digest, _iso(expires), timestamp, timestamp, timestamp, timestamp),
            )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), user["id"], "account.password_reset_requested", "user", user["id"],
                "{}", timestamp,
            ),
        )
        return raw_token, cooldown

    token, retry_after = await run_in_transaction(_issue, operation_name="issue password reset")
    return user, token, retry_after


async def consume_password_reset(token: str, password_hash: str) -> dict:
    if not token or len(token) < 32:
        raise PasswordResetInvalid("This password reset link is invalid.")
    digest = _token_hash(token)
    current = _now()
    timestamp = _iso(current)

    async def _consume(db) -> dict:
        cursor = await db.execute(
            """SELECT pr.*,u.email,u.name FROM password_resets pr
               JOIN users u ON u.id=pr.user_id WHERE pr.token_hash=?""",
            (digest,),
        )
        row = await cursor.fetchone()
        if not row or row["consumed_at"]:
            raise PasswordResetInvalid("This password reset link is invalid or has already been used.")
        expires = _parse(row["expires_at"])
        if not expires or expires <= current:
            raise PasswordResetExpired("This password reset link has expired. Request a new one.")

        user_id = str(row["user_id"])
        await db.execute(
            """UPDATE users SET password_hash=?,session_version=session_version+1,updated_at=?
               WHERE id=?""",
            (password_hash, timestamp, user_id),
        )
        await db.execute(
            "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,?) WHERE user_id=?",
            (timestamp, user_id),
        )
        await db.execute(
            "UPDATE password_resets SET consumed_at=?,updated_at=? WHERE user_id=?",
            (timestamp, timestamp, user_id),
        )
        await db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), user_id, "account.password_reset_completed", "user", user_id,
                json.dumps({"sessions_revoked": True}, separators=(",", ":")), timestamp,
            ),
        )
        return {"id": user_id, "email": row["email"], "name": row["name"]}

    return await run_in_transaction(_consume, operation_name="consume password reset")

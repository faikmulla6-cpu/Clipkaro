from datetime import datetime, timedelta, timezone
import logging

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response

from app.core.config import get_settings
from app.core.database import fetch_one
from app.services.account_security import session_is_active
from app.services.billing import sync_subscription_if_needed


hasher = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
security_logger = logging.getLogger("clipkaro.security")


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(user_id: str) -> str:
    """Legacy/test token helper.

    Production login/signup use create_session_token(), which adds a persisted
    session id and version. Tokens from this helper are accepted only in tests so
    older fixtures can remain focused on their own feature behavior.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.secret_key,
        algorithm="HS256",
    )


def set_auth_cookies(response: Response, token: str) -> None:
    settings = get_settings()
    secure = settings.app_env == "production"
    max_age = settings.access_token_minutes * 60
    response.set_cookie(
        "access_token", token, httponly=True, secure=secure, samesite="lax",
        max_age=max_age, path="/",
    )
    # Double-submit CSRF token must remain readable by browser JS. It is random,
    # scoped to this site, and is not an authentication credential by itself.
    import secrets
    response.set_cookie(
        "csrf_token", secrets.token_urlsafe(24), httponly=False, secure=secure,
        samesite="lax", max_age=max_age, path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("csrf_token", path="/")


def _request_token(request: Request, access_token: str | None = None, authorization: str | None = None) -> str | None:
    token = access_token or request.cookies.get("access_token")
    header = authorization or request.headers.get("Authorization")
    if header and header.lower().startswith("bearer "):
        token = header[7:]
    return token


def decode_request_session_id(request: Request, *, verify_exp: bool = True) -> str | None:
    token = _request_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=["HS256"],
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError:
        return None
    return str(payload.get("sid") or "") or None


def _is_manual_analysis_request(request: Request) -> bool:
    """Identify the internal/manual project analysis endpoint.

    The normal customer path is upload -> validated processing job -> transcript ->
    suggestions. `/analyse` exists only for internal QA, admin recovery and tests;
    it must never become a creator shortcut around Karo Minute reservation.
    """
    settings = get_settings()
    path = request.url.path.rstrip("/")
    prefix = f"{settings.api_prefix}/projects/"
    return request.method.upper() == "POST" and path.startswith(prefix) and path.endswith("/analyse")


def _manual_analysis_allowed(user: dict, settings) -> bool:
    """Fail closed for creator accounts unless access is explicitly internal.

    - Admins may use the endpoint for operational recovery in any environment.
    - Automated tests may use it so fixtures can exercise downstream logic.
    - Local development creators must explicitly opt in with
      ALLOW_MANUAL_ANALYSIS_IN_DEVELOPMENT=true.
    - Production, staging, preview and unknown environments deny creators.
    """
    if user.get("role") == "admin":
        return True
    if settings.app_env == "test":
        return True
    return settings.app_env == "development" and settings.allow_manual_analysis_in_development


async def current_user(
    request: Request,
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    token = _request_token(request, access_token, authorization)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Your session has expired. Please sign in again.") from exc

    user = await fetch_one("SELECT * FROM users WHERE id=?", (payload.get("sub"),))
    if not user:
        raise HTTPException(401, "Account not found.")

    settings = get_settings()
    session_id = str(payload.get("sid") or "")
    if session_id:
        if not await session_is_active(payload, user):
            raise HTTPException(401, "This session has been signed out. Please sign in again.")
        request.state.session_id = session_id
    elif settings.app_env != "test":
        # Deployment intentionally revokes the old stateless JWT generation.
        # A copied pre-hardening cookie must not remain usable for another week.
        raise HTTPException(401, "Your previous session was retired for security. Please sign in again.")

    user = await sync_subscription_if_needed(user)

    # `/analyse` can accept caller-provided transcript segments OR start direct
    # transcription. Both bypass the normal validated processing/reservation
    # workflow, so creator access is fail-closed before the route can execute.
    if _is_manual_analysis_request(request) and not _manual_analysis_allowed(user, settings):
        security_logger.warning(
            "Blocked manual analysis attempt user_id=%s role=%s app_env=%s",
            user.get("id"), user.get("role"), settings.app_env,
        )
        raise HTTPException(
            403,
            "Manual transcript analysis is restricted to ClipKaro internal/admin use. Use normal video processing.",
        )
    return user


def require_role(role: str):
    async def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] != role:
            raise HTTPException(403, "You do not have permission for this action.")
        return user
    return checker

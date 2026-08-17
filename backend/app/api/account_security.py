from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.database import fetch_one
from app.schemas.api import AuthOut, LoginRequest, UserOut
from app.services.auth import (
    clear_auth_cookies,
    current_user,
    decode_request_session_id,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from app.services.billing import sync_subscription_if_needed
from app.services.account_security import (
    PasswordResetDeliveryUnavailable,
    PasswordResetExpired,
    PasswordResetInvalid,
    consume_password_reset,
    create_session_token,
    issue_password_reset,
    list_active_sessions,
    revoke_all_sessions,
    revoke_session,
    send_password_reset_email,
)


router = APIRouter()
logger = logging.getLogger("clipkaro.security")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not any(c.isupper() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain an uppercase letter and a number.")
        return value


def _public_user(user: dict) -> UserOut:
    return UserOut(
        id=str(user["id"]),
        name=str(user["name"]),
        email=str(user["email"]),
        plan=str(user["plan"]),
        role=str(user["role"]),
        onboarding_complete=bool(user.get("onboarding_complete", 0)),
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _no_content(response: Response) -> Response:
    # Returning FastAPI's injected Response object overrides the decorator's
    # status code, so set 204 explicitly after cookie mutation.
    response.status_code = 204
    return response


@router.post("/auth/login", response_model=AuthOut)
async def login(body: LoginRequest, request: Request, response: Response) -> AuthOut:
    user = await fetch_one("SELECT * FROM users WHERE email=?", (body.email.lower(),))
    if not user or not verify_password(body.password, user["password_hash"]):
        # Keep account existence indistinguishable. The global auth/IP limiter in
        # main.py bounds online guessing before Argon2 can become a CPU DoS.
        raise HTTPException(401, "Incorrect email or password.")
    user = await sync_subscription_if_needed(user)
    token = await create_session_token(
        str(user["id"]),
        user_agent=request.headers.get("User-Agent", ""),
        client_ip=_client_ip(request),
    )
    set_auth_cookies(response, token)
    return AuthOut(user=_public_user(user))


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    # Logout is intentionally idempotent. Even an expired/revoked token gets its
    # browser cookies cleared, while a valid signed token also revokes its server
    # session so copying the old cookie cannot bring it back.
    session_id = decode_request_session_id(request, verify_exp=False)
    if session_id:
        await revoke_session(session_id)
    clear_auth_cookies(response)
    return _no_content(response)


@router.post("/auth/logout-all", status_code=204)
async def logout_all(request: Request, response: Response, user: dict = Depends(current_user)) -> Response:
    await revoke_all_sessions(str(user["id"]), increment_version=True)
    clear_auth_cookies(response)
    return _no_content(response)


@router.get("/auth/sessions")
async def sessions(request: Request, user: dict = Depends(current_user)) -> dict:
    current_session_id = str(getattr(request.state, "session_id", "") or "")
    return {"sessions": await list_active_sessions(str(user["id"]), current_session_id)}


@router.delete("/auth/sessions/{session_id}", status_code=204)
async def revoke_one_session(
    session_id: str,
    request: Request,
    response: Response,
    user: dict = Depends(current_user),
) -> Response:
    owned = await fetch_one(
        "SELECT id FROM auth_sessions WHERE id=? AND user_id=?",
        (session_id, user["id"]),
    )
    if not owned:
        raise HTTPException(404, "Session not found.")
    await revoke_session(session_id, str(user["id"]))
    if session_id == str(getattr(request.state, "session_id", "") or ""):
        clear_auth_cookies(response)
    return _no_content(response)


@router.post("/auth/password/forgot", status_code=202)
async def forgot_password(body: ForgotPasswordRequest) -> dict:
    # Always return the same response so this endpoint cannot be used to discover
    # registered email addresses. Per-account cooldowns are therefore also silent.
    user, token, _retry_after = await issue_password_reset(str(body.email))
    if user and token:
        try:
            await send_password_reset_email(str(user["email"]), str(user["name"]), token)
        except PasswordResetDeliveryUnavailable:
            logger.exception("Password reset delivery unavailable user_id=%s", user["id"])
    return {
        "accepted": True,
        "message": "If an account exists for that email, a password reset link will be sent shortly.",
    }


@router.post("/auth/password/reset")
async def reset_password(body: ResetPasswordRequest) -> dict:
    try:
        user = await consume_password_reset(body.token, hash_password(body.password))
    except PasswordResetExpired as exc:
        raise HTTPException(410, str(exc)) from exc
    except PasswordResetInvalid as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "reset": True,
        "email": str(user["email"]),
        "message": "Password reset complete. All existing ClipKaro sessions were signed out for safety.",
    }

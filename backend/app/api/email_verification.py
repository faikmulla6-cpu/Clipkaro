from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import get_settings
from app.schemas.api import SignupRequest
from app.services.auth import current_user, hash_password, set_auth_cookies
from app.services.account_security import create_session_token
from app.services.email_verification import (
    AccountAlreadyExists,
    EmailDeliveryUnavailable,
    VerificationRateLimited,
    VerificationTokenExpired,
    VerificationTokenInvalid,
    consume_verification_token,
    create_unverified_account,
    email_delivery_configured,
    issue_resend_token,
    send_verification_email,
    verification_status,
)
from app.services.legal import (
    LEGAL_VERSION,
    legal_controls_required,
    record_legal_acceptance,
)


router = APIRouter()
logger = logging.getLogger("clipkaro.email")


def _public_user(user: dict) -> dict:
    return {
        "id": str(user["id"]),
        "name": str(user["name"]),
        "email": str(user["email"]),
        "plan": str(user["plan"]),
        "role": str(user["role"]),
        "onboarding_complete": bool(user.get("onboarding_complete", 0)),
    }


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.post("/auth/signup", status_code=201)
async def signup_with_verification(body: SignupRequest, request: Request, response: Response) -> dict:
    settings = get_settings()

    # Infrastructure readiness is checked before request-level legal validation.
    # If production-like mail delivery is unavailable, account creation must be
    # paused for every request rather than returning a body-dependent validation
    # result for an operation that cannot safely complete anyway.
    if (
        settings.email_verification_required
        and settings.app_env not in {"development", "test"}
        and not email_delivery_configured()
    ):
        raise HTTPException(
            503,
            "Email verification is temporarily unavailable. Account creation is paused until mail delivery is configured.",
        )

    # Once signup infrastructure is healthy, production-like environments require
    # an affirmative acceptance of the exact current legal document set before an
    # account row or creator session is created.
    if legal_controls_required():
        if body.accept_legal is not True:
            raise HTTPException(
                422,
                "Review and accept the current Terms, Privacy Notice and Refund Policy before creating an account.",
            )
        if body.legal_version != LEGAL_VERSION:
            raise HTTPException(
                409,
                "The legal documents changed. Refresh signup and review the latest version before continuing.",
            )

    try:
        user, raw_token = await create_unverified_account(
            body.name.strip(), body.email.lower(), hash_password(body.password),
        )
    except AccountAlreadyExists as exc:
        raise HTTPException(409, "An account already exists for this email.") from exc

    # Record the exact document set the creator affirmatively accepted. In the
    # test/development sandbox this remains optional so fixture accounts do not
    # have to impersonate real-world legal consent.
    if body.accept_legal:
        if body.legal_version != LEGAL_VERSION:
            raise HTTPException(409, "The legal document version is no longer current.")
        await record_legal_acceptance(
            str(user["id"]),
            LEGAL_VERSION,
            source="signup",
            user_agent=request.headers.get("User-Agent", ""),
        )

    sent = False
    if settings.email_verification_required and user.get("role") != "admin":
        try:
            await send_verification_email(str(user["email"]), str(user["name"]), raw_token)
            sent = True
        except EmailDeliveryUnavailable:
            # The account remains safely unverified. This is preferable to
            # deleting an account after an SMTP server may already have accepted
            # the message. The creator can sign in and resend when delivery recovers.
            logger.exception("Initial verification email delivery failed user_id=%s", user["id"])
    else:
        # Verification can be disabled explicitly for a non-production sandbox.
        from app.core.database import execute
        from datetime import datetime, timezone

        verified_at = datetime.now(timezone.utc).isoformat()
        await execute(
            "UPDATE users SET email_verified_at=?,updated_at=? WHERE id=?",
            (verified_at, verified_at, user["id"]),
        )
        user["email_verified_at"] = verified_at

    session_token = await create_session_token(
        str(user["id"]),
        user_agent=request.headers.get("User-Agent", ""),
        client_ip=_client_ip(request),
    )
    set_auth_cookies(response, session_token)
    return {
        "user": _public_user(user),
        "token_type": "cookie",
        "verification_email_sent": sent,
        "verification": verification_status(user),
    }


@router.get("/auth/verification-status")
async def get_verification_status(user: dict = Depends(current_user)) -> dict:
    return verification_status(user)


@router.post("/auth/verify-email")
async def verify_email(body: dict) -> dict:
    token = str(body.get("token") or "")
    try:
        user = await consume_verification_token(token)
    except VerificationTokenExpired as exc:
        raise HTTPException(410, str(exc)) from exc
    except VerificationTokenInvalid as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "verified": True,
        "email": str(user.get("email") or ""),
        "already_verified": bool(user.get("_verification_reused")),
        "message": (
            "This email was already verified. AI processing remains unlocked for this account."
            if user.get("_verification_reused")
            else "Email verified. AI processing is now unlocked for this account."
        ),
    }


@router.post("/auth/resend-verification")
async def resend_verification(user: dict = Depends(current_user)) -> dict:
    if user.get("email_verified_at"):
        return {"sent": False, "verified": True, "retry_after": 0}
    if not get_settings().email_verification_required:
        return {"sent": False, "verified": True, "retry_after": 0}

    try:
        fresh_user, raw_token, retry_after = await issue_resend_token(str(user["id"]))
    except VerificationRateLimited as exc:
        raise HTTPException(
            429, str(exc), headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except VerificationTokenInvalid as exc:
        raise HTTPException(404, "Account not found.") from exc

    if raw_token is None:
        return {"sent": False, "verified": True, "retry_after": 0}
    try:
        await send_verification_email(
            str(fresh_user["email"]), str(fresh_user["name"]), raw_token,
        )
    except EmailDeliveryUnavailable as exc:
        raise HTTPException(
            503,
            "Verification email could not be sent right now. Please retry after the cooldown.",
        ) from exc
    return {"sent": True, "verified": False, "retry_after": retry_after}

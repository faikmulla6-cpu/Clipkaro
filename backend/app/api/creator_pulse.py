from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.database import distributed_advisory_lock, execute, fetch_all, fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.billing import parse_iso, razorpay_request, utc_now, verify_order_signature
from app.services.legal import checkout_allowed, has_current_legal_acceptance
from app.services.email_verification import requires_verification_for_processing


router = APIRouter()

PULSE_PRICE_PAISE = 100
PULSE_TOPUP_OPTIONS = {10: 1000, 20: 2000, 50: 5000}
PULSE_RECENT_VIDEO_LIMIT = 10
PULSE_CHECKOUT_REUSE_MINUTES = 15
PULSE_DAILY_USER_LIMIT = 25
PULSE_MIN_RESCAN_SECONDS = 60
PULSE_STALE_PROCESSING_SECONDS = 300

_user_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_checkout_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


class PulseProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502, code: str = "YOUTUBE_UNAVAILABLE") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


async def init_creator_pulse() -> None:
    """Install additive Pulse tables for SQLite development/test databases.

    PostgreSQL schema changes are owned by Alembic and are checked at boot by
    ``init_db``. Keeping runtime DDL out of production prevents schema drift.
    """
    if get_settings().normalized_database_backend == "postgres":
        return
    statements = [
        """CREATE TABLE IF NOT EXISTS creator_pulse_wallets (
             user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
             balance_paise INTEGER NOT NULL DEFAULT 0 CHECK(balance_paise >= 0),
             created_at TEXT NOT NULL, updated_at TEXT NOT NULL
           )""",
        """CREATE TABLE IF NOT EXISTS creator_pulse_checkouts (
             id TEXT PRIMARY KEY,
             user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
             provider_reference TEXT NOT NULL UNIQUE,
             amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
             status TEXT NOT NULL CHECK(status IN ('created','authorized','verified','failed','expired')),
             payment_id TEXT, created_at TEXT NOT NULL, verified_at TEXT
           )""",
        """CREATE INDEX IF NOT EXISTS idx_creator_pulse_checkouts_user
           ON creator_pulse_checkouts(user_id, created_at DESC)""",
        """CREATE TABLE IF NOT EXISTS creator_pulse_transactions (
             id TEXT PRIMARY KEY,
             user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
             kind TEXT NOT NULL CHECK(kind IN ('topup','pulse_charge','pulse_refund')),
             delta_paise INTEGER NOT NULL,
             balance_after_paise INTEGER NOT NULL CHECK(balance_after_paise >= 0),
             reference TEXT NOT NULL UNIQUE,
             metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
           )""",
        """CREATE INDEX IF NOT EXISTS idx_creator_pulse_transactions_user
           ON creator_pulse_transactions(user_id, created_at DESC)""",
        """CREATE TABLE IF NOT EXISTS creator_pulse_scans (
             id TEXT PRIMARY KEY,
             user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
             request_key TEXT NOT NULL, handle TEXT NOT NULL,
             channel_id TEXT, channel_title TEXT, subscriber_count INTEGER,
             total_views INTEGER NOT NULL DEFAULT 0, video_count INTEGER NOT NULL DEFAULT 0,
             status TEXT NOT NULL CHECK(status IN ('processing','completed','failed')),
             charged_paise INTEGER NOT NULL DEFAULT 0 CHECK(charged_paise >= 0),
             snapshot_json TEXT NOT NULL DEFAULT '{}', error_code TEXT,
             captured_at TEXT, created_at TEXT NOT NULL,
             UNIQUE(user_id, request_key)
           )""",
        """CREATE INDEX IF NOT EXISTS idx_creator_pulse_scans_history
           ON creator_pulse_scans(user_id, channel_id, captured_at DESC)""",
    ]
    for statement in statements:
        await execute(statement)


async def _audit(user_id: str | None, event: str, entity_type: str, entity_id: str, metadata: dict[str, Any] | None = None) -> None:
    await execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, event, entity_type, entity_id, json.dumps(metadata or {}, separators=(",", ":")), utc_now().isoformat()),
    )


def _youtube_api_key() -> str:
    return get_settings().youtube_data_api_key.strip()


def _youtube_timeout_seconds() -> float:
    try:
        return min(max(float(get_settings().youtube_data_api_timeout_seconds), 3.0), 8.0)
    except (TypeError, ValueError):
        return 7.0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_handle(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(422, "Enter a YouTube @handle or channel URL.")
    if len(raw) > 240:
        raise HTTPException(422, "The YouTube channel value is too long.")
    if "youtube.com" in raw.lower():
        candidate = raw if "://" in raw else f"https://{raw}"
        try:
            parsed = urlparse(candidate)
        except ValueError as exc:
            raise HTTPException(422, "Enter a valid YouTube @handle or channel URL.") from exc
        match = re.search(r"/@([^/?#]+)", parsed.path)
        if not match:
            raise HTTPException(422, "Use a YouTube @handle URL such as youtube.com/@channel.")
        raw = match.group(1)
    raw = raw.lstrip("@").strip()
    if not re.fullmatch(r"[\w.-]{3,100}", raw, flags=re.UNICODE):
        raise HTTPException(422, "Enter a valid YouTube @handle.")
    return f"@{raw}"


def _validate_request_key(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, "Creator Pulse request identity is invalid. Refresh and try again.") from exc
    return str(parsed)


def _best_thumbnail(thumbnails: Any) -> str | None:
    if not isinstance(thumbnails, dict):
        return None
    for key in ("maxres", "standard", "high", "medium", "default"):
        item = thumbnails.get(key)
        if isinstance(item, dict) and str(item.get("url") or "").startswith("https://"):
            return str(item["url"])
    return None


async def _youtube_get(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
    api_key = _youtube_api_key()
    if not api_key:
        raise PulseProviderError(
            "Creator Pulse is not connected to YouTube yet.", status_code=503, code="YOUTUBE_NOT_CONFIGURED"
        )
    safe_params = {**params, "key": api_key}
    try:
        response = await client.get(f"https://www.googleapis.com/youtube/v3/{path}", params=safe_params)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise PulseProviderError("YouTube could not be reached. Your ₹1 Pulse was not charged.") from exc
    if response.status_code == 403:
        raise PulseProviderError(
            "YouTube could not serve this Pulse right now. API quota or server credentials may need attention. Your ₹1 was refunded.",
            status_code=503,
            code="YOUTUBE_QUOTA_OR_AUTH",
        )
    if response.status_code in {400, 404}:
        raise PulseProviderError(
            "YouTube could not find that public channel. Check the @handle and try again. Your ₹1 was refunded.",
            status_code=404,
            code="CHANNEL_NOT_FOUND",
        )
    if response.status_code >= 500:
        raise PulseProviderError("YouTube is temporarily unavailable. Your ₹1 Pulse was refunded.")
    if response.status_code >= 400:
        raise PulseProviderError("YouTube rejected this request. Your ₹1 Pulse was refunded.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise PulseProviderError("YouTube returned an invalid response. Your ₹1 Pulse was refunded.") from exc
    if not isinstance(payload, dict):
        raise PulseProviderError("YouTube returned an invalid response. Your ₹1 Pulse was refunded.")
    return payload


async def _fetch_youtube_snapshot(handle: str) -> dict[str, Any]:
    now = utc_now()
    async with httpx.AsyncClient(timeout=_youtube_timeout_seconds(), headers={"User-Agent": "ClipKaro-Creator-Pulse/1.0"}) as client:
        channel_payload = await _youtube_get(
            client,
            "channels",
            {"part": "snippet,statistics,contentDetails", "forHandle": handle.lstrip("@"), "maxResults": 1},
        )
        items = channel_payload.get("items") or []
        if not items:
            raise PulseProviderError(
                "YouTube could not find that public channel. Check the @handle and try again. Your ₹1 was refunded.",
                status_code=404,
                code="CHANNEL_NOT_FOUND",
            )
        channel = items[0]
        snippet = channel.get("snippet") or {}
        statistics_payload = channel.get("statistics") or {}
        related = ((channel.get("contentDetails") or {}).get("relatedPlaylists") or {})
        uploads_playlist = str(related.get("uploads") or "")
        channel_id = str(channel.get("id") or "")
        if not channel_id or not uploads_playlist:
            raise PulseProviderError("This channel does not expose a usable uploads feed. Your ₹1 was refunded.", code="UPLOADS_UNAVAILABLE")

        playlist_payload = await _youtube_get(
            client,
            "playlistItems",
            {"part": "snippet,contentDetails", "playlistId": uploads_playlist, "maxResults": PULSE_RECENT_VIDEO_LIMIT},
        )
        playlist_items = playlist_payload.get("items") or []
        video_ids: list[str] = []
        playlist_by_video: dict[str, dict[str, Any]] = {}
        for item in playlist_items:
            content = item.get("contentDetails") or {}
            item_snippet = item.get("snippet") or {}
            video_id = str(content.get("videoId") or (item_snippet.get("resourceId") or {}).get("videoId") or "")
            if video_id and video_id not in playlist_by_video:
                video_ids.append(video_id)
                playlist_by_video[video_id] = item
        if not video_ids:
            raise PulseProviderError("This channel has no public recent uploads to analyse. Your ₹1 was refunded.", status_code=409, code="NO_PUBLIC_UPLOADS")

        videos_payload = await _youtube_get(
            client,
            "videos",
            {"part": "snippet,statistics", "id": ",".join(video_ids)},
        )
        provider_videos = {str(item.get("id") or ""): item for item in (videos_payload.get("items") or [])}

    recent_videos: list[dict[str, Any]] = []
    for video_id in video_ids:
        item = provider_videos.get(video_id)
        if not item:
            continue
        video_snippet = item.get("snippet") or {}
        fallback_snippet = (playlist_by_video.get(video_id) or {}).get("snippet") or {}
        stats = item.get("statistics") or {}
        published_at = str(video_snippet.get("publishedAt") or fallback_snippet.get("publishedAt") or "")
        published = _parse_datetime(published_at)
        age_days = max(0.25, (now - published).total_seconds() / 86400.0) if published else 0.25
        views = _safe_int(stats.get("viewCount"))
        likes = _safe_int(stats.get("likeCount")) if "likeCount" in stats else None
        comments = _safe_int(stats.get("commentCount")) if "commentCount" in stats else None
        engagement = ((likes + comments) / views * 100.0) if views > 0 and likes is not None and comments is not None else None
        recent_videos.append(
            {
                "id": video_id,
                "title": str(video_snippet.get("title") or fallback_snippet.get("title") or "Untitled upload")[:300],
                "published_at": published_at,
                "thumbnail_url": _best_thumbnail(video_snippet.get("thumbnails") or fallback_snippet.get("thumbnails")),
                "views": views,
                "likes": likes,
                "comments": comments,
                "age_days": round(age_days, 2),
                "views_per_day": round(views / age_days, 2),
                "engagement_rate": round(engagement, 4) if engagement is not None else None,
            }
        )

    if not recent_videos:
        raise PulseProviderError("This channel has no public recent videos available for analysis. Your ₹1 was refunded.", status_code=409, code="NO_PUBLIC_VIDEO_STATS")

    average_views = round(sum(item["views"] for item in recent_videos) / len(recent_videos))
    engagement_values = [float(item["engagement_rate"]) for item in recent_videos if item["engagement_rate"] is not None]
    average_engagement = round(sum(engagement_values) / len(engagement_values), 4) if engagement_values else None
    for item in recent_videos:
        item["vs_recent_average_pct"] = round(((item["views"] - average_views) / average_views * 100.0), 2) if average_views else 0.0

    published_values = [parsed for parsed in (_parse_datetime(str(item["published_at"])) for item in recent_videos) if parsed]
    published_values.sort(reverse=True)
    cadence_intervals = [
        (published_values[index] - published_values[index + 1]).total_seconds() / 86400.0
        for index in range(len(published_values) - 1)
        if published_values[index] > published_values[index + 1]
    ]
    cadence_days = round(statistics.median(cadence_intervals), 2) if cadence_intervals else None

    hidden_subscribers = bool(statistics_payload.get("hiddenSubscriberCount", False))
    subscriber_count = None if hidden_subscribers or "subscriberCount" not in statistics_payload else _safe_int(statistics_payload.get("subscriberCount"))
    return {
        "channel": {
            "id": channel_id,
            "handle": handle,
            "title": str(snippet.get("title") or handle)[:200],
            "description": str(snippet.get("description") or "")[:1200],
            "thumbnail_url": _best_thumbnail(snippet.get("thumbnails")),
            "subscribers": subscriber_count,
            "hidden_subscriber_count": hidden_subscribers,
            "total_views": _safe_int(statistics_payload.get("viewCount")),
            "video_count": _safe_int(statistics_payload.get("videoCount")),
        },
        "recent": {
            "average_views": average_views,
            "average_engagement_rate": average_engagement,
            "upload_cadence_days": cadence_days,
            "videos": recent_videos,
        },
    }


def _build_insights(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    videos = list((snapshot.get("recent") or {}).get("videos") or [])
    if not videos:
        return []
    insights: list[dict[str, str]] = []
    momentum = max(videos, key=lambda item: float(item.get("views_per_day") or 0))
    insights.append(
        {
            "key": "momentum",
            "label": "FASTEST MOMENTUM",
            "title": str(momentum.get("title") or "Recent upload")[:120],
            "detail": f"{_safe_int(round(float(momentum.get('views_per_day') or 0))):,} public views/day since publish.",
            "tone": "positive",
        }
    )
    engagement_videos = [item for item in videos if item.get("engagement_rate") is not None]
    if engagement_videos:
        strongest = max(engagement_videos, key=lambda item: float(item.get("engagement_rate") or 0))
        insights.append(
            {
                "key": "engagement",
                "label": "STRONGEST ENGAGEMENT",
                "title": str(strongest.get("title") or "Recent upload")[:120],
                "detail": f"{float(strongest['engagement_rate']):.2f}% likes + comments relative to public views.",
                "tone": "positive",
            }
        )
    weakest = min(videos, key=lambda item: float(item.get("vs_recent_average_pct") or 0))
    weakest_pct = float(weakest.get("vs_recent_average_pct") or 0)
    if weakest_pct <= -20:
        insights.append(
            {
                "key": "below_average",
                "label": "WATCH",
                "title": str(weakest.get("title") or "Recent upload")[:120],
                "detail": f"Current public views are {abs(weakest_pct):.0f}% below the recent-upload average. Age still matters, so treat this as a signal, not a verdict.",
                "tone": "watch",
            }
        )
    cadence = (snapshot.get("recent") or {}).get("upload_cadence_days")
    if cadence is not None:
        insights.append(
            {
                "key": "cadence",
                "label": "UPLOAD CADENCE",
                "title": f"About every {float(cadence):.1f} days",
                "detail": "Median gap across the recent public uploads in this Pulse.",
                "tone": "neutral",
            }
        )
    return insights[:4]


async def _wallet_balance(user_id: str) -> int:
    row = await fetch_one("SELECT balance_paise FROM creator_pulse_wallets WHERE user_id=?", (user_id,))
    return _safe_int((row or {}).get("balance_paise"))


async def _ensure_wallet(user_id: str) -> None:
    now = utc_now().isoformat()
    await execute(
        """INSERT INTO creator_pulse_wallets(user_id,balance_paise,created_at,updated_at)
           VALUES (?,0,?,?) ON CONFLICT(user_id) DO NOTHING""",
        (user_id, now, now),
    )


async def _completed_scan_payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(row.get("snapshot_json") or "{}"))
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(500, "Saved Creator Pulse evidence is unreadable.")
    if not isinstance(payload, dict):
        raise HTTPException(500, "Saved Creator Pulse evidence is unreadable.")
    payload["balance_paise"] = await _wallet_balance(str(row["user_id"]))
    return payload


async def _recover_stale_processing(user_id: str) -> None:
    """Refund a charge left processing after an API/container crash.

    The normal request path refunds immediately on provider/application errors.
    This recovery path is for abrupt process loss where exception handling never
    ran. Transactions are idempotent, so concurrent recovery cannot mint balance.
    """
    cutoff = (utc_now() - timedelta(seconds=PULSE_STALE_PROCESSING_SECONDS)).isoformat()
    stale = await fetch_all(
        "SELECT id,request_key FROM creator_pulse_scans WHERE user_id=? AND status='processing' AND created_at<?",
        (user_id, cutoff),
    )
    for row in stale:
        await _refund_pulse(str(row["id"]), str(row["request_key"]), "STALE_PROCESSING_RECOVERY")


@router.get("/creator-pulse/status")
async def creator_pulse_status(user: dict = Depends(current_user)) -> dict[str, Any]:
    await _ensure_wallet(str(user["id"]))
    await _recover_stale_processing(str(user["id"]))
    recent = await fetch_all(
        """SELECT id,channel_title,handle,captured_at,total_views,subscriber_count
           FROM creator_pulse_scans WHERE user_id=? AND status='completed'
           ORDER BY captured_at DESC LIMIT 6""",
        (user["id"],),
    )
    return {
        "balance_paise": await _wallet_balance(str(user["id"])),
        "price_paise": PULSE_PRICE_PAISE,
        "topup_options_rupees": sorted(PULSE_TOPUP_OPTIONS),
        "youtube_configured": bool(_youtube_api_key()),
        "recent_scans": [
            {
                "id": row["id"],
                "channel_title": row.get("channel_title") or row.get("handle") or "YouTube channel",
                "handle": row.get("handle") or "",
                "captured_at": row.get("captured_at"),
                "total_views": _safe_int(row.get("total_views")),
                "subscribers": row.get("subscriber_count"),
            }
            for row in recent
        ],
    }


async def _require_topup_ready(user_id: str) -> None:
    allowed, reason = checkout_allowed()
    if not allowed:
        raise HTTPException(403, reason)
    if not await has_current_legal_acceptance(user_id):
        raise HTTPException(403, "Accept the current ClipKaro Terms, Privacy Notice and Refund Policy from Plans & billing before adding Pulse Balance.")
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(503, "Razorpay is not configured on the server.")


@router.post("/creator-pulse/balance/checkout")
async def creator_pulse_checkout(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    try:
        rupees = int(body.get("amount_rupees"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Choose a valid Pulse Balance amount.") from exc
    amount_paise = PULSE_TOPUP_OPTIONS.get(rupees)
    if amount_paise is None:
        raise HTTPException(422, "Choose ₹10, ₹20 or ₹50 for Pulse Balance.")
    user_id = str(user["id"])
    if requires_verification_for_processing(user):
        raise HTTPException(403, "Verify your email before adding Pulse Balance.")
    await _require_topup_ready(user_id)
    async with _checkout_locks[user_id], distributed_advisory_lock(f"creator-pulse-checkout:{user_id}"):
        cutoff = (utc_now() - timedelta(minutes=PULSE_CHECKOUT_REUSE_MINUTES)).isoformat()
        await execute(
            """UPDATE creator_pulse_checkouts SET status='expired'
               WHERE user_id=? AND amount_paise=? AND status IN ('created','authorized') AND created_at<?""",
            (user_id, amount_paise, cutoff),
        )
        reusable = await fetch_one(
            """SELECT * FROM creator_pulse_checkouts
               WHERE user_id=? AND amount_paise=? AND status IN ('created','authorized')
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, amount_paise),
        )
        if reusable:
            reference = str(reusable["provider_reference"])
        else:
            receipt = f"pulse_{user_id[:8]}_{uuid.uuid4().hex[:12]}"
            try:
                order = await razorpay_request(
                    "POST",
                    "/orders",
                    json_body={
                        "amount": amount_paise,
                        "currency": "INR",
                        "receipt": receipt,
                        "notes": {
                            "user_id": user_id,
                            "product": "ClipKaro Creator Pulse",
                            "purpose": "pulse_balance",
                            "amount_paise": str(amount_paise),
                        },
                    },
                )
            except RuntimeError as exc:
                raise HTTPException(502, "Razorpay could not start the Pulse Balance top-up. Please retry.") from exc
            reference = str(order.get("id") or "")
            if not reference:
                raise HTTPException(502, "Razorpay did not return a valid Order ID.")
            await execute(
                """INSERT INTO creator_pulse_checkouts(
                     id,user_id,provider_reference,amount_paise,status,payment_id,created_at,verified_at
                   ) VALUES (?,?,?,?, 'created',NULL,?,NULL)""",
                (str(uuid.uuid4()), user_id, reference, amount_paise, utc_now().isoformat()),
            )
            await _audit(user_id, "creator_pulse.topup_created", "creator_pulse_checkout", reference, {"amount_paise": amount_paise})
    settings = get_settings()
    return {
        "key_id": settings.razorpay_key_id,
        "order_id": reference,
        "amount": amount_paise,
        "currency": "INR",
        "name": "ClipKaro Creator Pulse",
        "description": f"₹{rupees} Pulse Balance · ₹1 per successful analysis · no subscription",
        "prefill": {"name": user["name"], "email": user["email"]},
    }


def _payment_matches_pulse_checkout(payment: dict[str, Any], checkout: dict[str, Any], payment_id: str) -> tuple[bool, bool]:
    valid = bool(
        str(payment.get("id") or "") == payment_id
        and str(payment.get("order_id") or "") == str(checkout.get("provider_reference") or "")
        and _safe_int(payment.get("amount")) == _safe_int(checkout.get("amount_paise"))
        and str(payment.get("currency") or "").upper() == "INR"
    )
    captured = valid and str(payment.get("status") or "").lower() == "captured" and bool(payment.get("captured", True))
    return valid, captured


async def _credit_verified_checkout(checkout_id: str, *, payment_id: str | None) -> tuple[bool, int, int]:
    async def _credit(db) -> tuple[bool, int, int]:
        cursor = await db.execute("SELECT * FROM creator_pulse_checkouts WHERE id=?", (checkout_id,))
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Pulse checkout disappeared during verification.")
        checkout = dict(row)
        user_id = str(checkout["user_id"])
        amount = _safe_int(checkout["amount_paise"])
        now = utc_now().isoformat()
        await db.execute(
            """INSERT INTO creator_pulse_wallets(user_id,balance_paise,created_at,updated_at)
               VALUES (?,0,?,?) ON CONFLICT(user_id) DO NOTHING""",
            (user_id, now, now),
        )
        wallet_cursor = await db.execute("SELECT balance_paise FROM creator_pulse_wallets WHERE user_id=?", (user_id,))
        wallet_row = await wallet_cursor.fetchone()
        current_balance = _safe_int(dict(wallet_row)["balance_paise"] if wallet_row else 0)
        if str(checkout.get("status") or "") == "verified":
            return False, amount, current_balance
        new_balance = current_balance + amount
        await db.execute(
            "UPDATE creator_pulse_wallets SET balance_paise=?,updated_at=? WHERE user_id=?",
            (new_balance, now, user_id),
        )
        await db.execute(
            """UPDATE creator_pulse_checkouts SET status='verified',payment_id=COALESCE(?,payment_id),verified_at=?
               WHERE id=?""",
            (payment_id or None, now, checkout_id),
        )
        await db.execute(
            """INSERT INTO creator_pulse_transactions(
                 id,user_id,kind,delta_paise,balance_after_paise,reference,metadata_json,created_at
               ) VALUES (?,?, 'topup',?,?,?,?,?)""",
            (
                str(uuid.uuid4()), user_id, amount, new_balance,
                f"topup:{checkout['provider_reference']}",
                json.dumps({"provider_reference": checkout["provider_reference"]}, separators=(",", ":")),
                now,
            ),
        )
        return True, amount, new_balance

    return await run_in_transaction(_credit, mode="IMMEDIATE", operation_name="credit Creator Pulse balance")


@router.post("/creator-pulse/balance/verify")
async def creator_pulse_verify(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    payment_id = str(body.get("razorpay_payment_id") or "")
    order_id = str(body.get("razorpay_order_id") or "")
    signature = str(body.get("razorpay_signature") or "")
    if not payment_id or not order_id or not signature:
        raise HTTPException(422, "Razorpay payment verification data is incomplete.")
    checkout = await fetch_one(
        "SELECT * FROM creator_pulse_checkouts WHERE provider_reference=? AND user_id=?",
        (order_id, user["id"]),
    )
    if not checkout:
        raise HTTPException(404, "This Pulse Balance checkout does not belong to your account.")
    if checkout.get("status") == "verified":
        return {"verified": True, "credited_paise": _safe_int(checkout.get("amount_paise")), "balance_paise": await _wallet_balance(str(user["id"]))}
    if not verify_order_signature(order_id, payment_id, signature):
        raise HTTPException(400, "Payment signature verification failed.")
    try:
        payment = await razorpay_request("GET", f"/payments/{payment_id}")
    except RuntimeError as exc:
        raise HTTPException(502, "Payment was authenticated, but Razorpay capture status could not be confirmed yet.") from exc
    identity_valid, captured = _payment_matches_pulse_checkout(payment, checkout, payment_id)
    if not identity_valid:
        raise HTTPException(400, "Payment details did not match this Pulse Balance checkout.")
    if not captured:
        await execute(
            "UPDATE creator_pulse_checkouts SET status='authorized',payment_id=? WHERE id=? AND status!='verified'",
            (payment_id, checkout["id"]),
        )
        return {"verified": True, "credited_paise": 0, "balance_paise": await _wallet_balance(str(user["id"]))}
    async with distributed_advisory_lock(f"creator-pulse-topup:{order_id}"):
        _, amount, balance = await _credit_verified_checkout(str(checkout["id"]), payment_id=payment_id)
    await _audit(str(user["id"]), "creator_pulse.topup_verified", "creator_pulse_checkout", order_id, {"amount_paise": amount})
    return {"verified": True, "credited_paise": amount, "balance_paise": balance}


async def reconcile_creator_pulse_webhook(event_type: str, payment: dict[str, Any], order: dict[str, Any]) -> dict[str, Any] | None:
    """Reconcile a signed Razorpay event after the shared webhook verifies HMAC.

    Returns ``None`` when the provider order does not belong to Creator Pulse,
    allowing the normal ClipKaro billing lifecycle to continue independently.
    """
    reference = str(payment.get("order_id") or order.get("id") or "")
    if not reference:
        return None
    checkout = await fetch_one("SELECT * FROM creator_pulse_checkouts WHERE provider_reference=?", (reference,))
    if not checkout:
        return None
    user_id = str(checkout["user_id"])
    amount = _safe_int(checkout["amount_paise"])
    payment_id = str(payment.get("id") or checkout.get("payment_id") or "") or None
    if event_type in {"payment.authorized", "payment.failed"}:
        if str(payment.get("order_id") or "") != reference or _safe_int(payment.get("amount")) != amount or str(payment.get("currency") or "").upper() != "INR":
            return {"user_id": user_id, "status": "rejected_pulse_payment_mismatch", "amount": amount}
        expected = "authorized" if event_type == "payment.authorized" else "failed"
        if str(payment.get("status") or "") != expected:
            return {"user_id": user_id, "status": "rejected_pulse_payment_state", "amount": amount}
        await execute(
            "UPDATE creator_pulse_checkouts SET status=?,payment_id=COALESCE(?,payment_id) WHERE id=? AND status!='verified'",
            (expected, payment_id, checkout["id"]),
        )
        return {"user_id": user_id, "status": expected, "amount": amount}
    if event_type not in {"payment.captured", "order.paid"}:
        return {"user_id": user_id, "status": "pulse_event_received", "amount": amount}
    valid = False
    if event_type == "payment.captured":
        valid = bool(
            str(payment.get("order_id") or "") == reference
            and str(payment.get("status") or "") == "captured"
            and _safe_int(payment.get("amount")) == amount
            and str(payment.get("currency") or "").upper() == "INR"
        )
    else:
        valid = bool(
            str(order.get("id") or "") == reference
            and str(order.get("status") or "") == "paid"
            and _safe_int(order.get("amount_paid") or order.get("amount")) == amount
            and str(order.get("currency") or "").upper() == "INR"
        )
        if payment:
            valid = valid and str(payment.get("status") or "captured") == "captured"
    if not valid:
        return {"user_id": user_id, "status": "rejected_pulse_capture_mismatch", "amount": amount}
    async with distributed_advisory_lock(f"creator-pulse-topup:{reference}"):
        credited, _, _ = await _credit_verified_checkout(str(checkout["id"]), payment_id=payment_id)
    if credited:
        await _audit(user_id, "creator_pulse.topup_webhook_verified", "creator_pulse_checkout", reference, {"amount_paise": amount, "event": event_type})
    return {"user_id": user_id, "status": "verified", "amount": amount}


class PulseBalanceInsufficient(RuntimeError):
    pass


class PulseDuplicate(RuntimeError):
    pass


async def _reserve_pulse(user_id: str, handle: str, request_key: str) -> str:
    scan_id = str(uuid.uuid4())
    now = utc_now()

    async def _reserve(db) -> str:
        await db.execute(
            """INSERT INTO creator_pulse_wallets(user_id,balance_paise,created_at,updated_at)
               VALUES (?,0,?,?) ON CONFLICT(user_id) DO NOTHING""",
            (user_id, now.isoformat(), now.isoformat()),
        )
        existing_cursor = await db.execute(
            "SELECT id,status FROM creator_pulse_scans WHERE user_id=? AND request_key=?",
            (user_id, request_key),
        )
        existing = await existing_cursor.fetchone()
        if existing:
            raise PulseDuplicate(str(dict(existing).get("status") or "processing"))
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).isoformat()
        count_cursor = await db.execute(
            "SELECT COUNT(*) AS count FROM creator_pulse_scans WHERE user_id=? AND status='completed' AND captured_at>=?",
            (user_id, day_start),
        )
        count_row = await count_cursor.fetchone()
        if _safe_int(dict(count_row).get("count") if count_row else 0) >= PULSE_DAILY_USER_LIMIT:
            raise HTTPException(429, f"Creator Pulse is limited to {PULSE_DAILY_USER_LIMIT} successful checks per account per day while the YouTube quota is protected.")
        recent_cursor = await db.execute(
            """SELECT captured_at FROM creator_pulse_scans
               WHERE user_id=? AND handle=? AND status='completed' ORDER BY captured_at DESC LIMIT 1""",
            (user_id, handle),
        )
        recent = await recent_cursor.fetchone()
        if recent:
            captured = parse_iso(str(dict(recent).get("captured_at") or ""))
            if captured and (now - captured).total_seconds() < PULSE_MIN_RESCAN_SECONDS:
                raise HTTPException(429, "This channel was just checked. Wait one minute before paying for another Pulse.")
        wallet_cursor = await db.execute("SELECT balance_paise FROM creator_pulse_wallets WHERE user_id=?", (user_id,))
        wallet_row = await wallet_cursor.fetchone()
        balance = _safe_int(dict(wallet_row).get("balance_paise") if wallet_row else 0)
        if balance < PULSE_PRICE_PAISE:
            raise PulseBalanceInsufficient()
        new_balance = balance - PULSE_PRICE_PAISE
        await db.execute(
            "UPDATE creator_pulse_wallets SET balance_paise=?,updated_at=? WHERE user_id=?",
            (new_balance, now.isoformat(), user_id),
        )
        await db.execute(
            """INSERT INTO creator_pulse_scans(
                 id,user_id,request_key,handle,channel_id,channel_title,subscriber_count,total_views,video_count,
                 status,charged_paise,snapshot_json,error_code,captured_at,created_at
               ) VALUES (?,?,?,?,NULL,NULL,NULL,0,0,'processing',?,'{}',NULL,NULL,?)""",
            (scan_id, user_id, request_key, handle, PULSE_PRICE_PAISE, now.isoformat()),
        )
        await db.execute(
            """INSERT INTO creator_pulse_transactions(
                 id,user_id,kind,delta_paise,balance_after_paise,reference,metadata_json,created_at
               ) VALUES (?,?, 'pulse_charge',?,?,?,?,?)""",
            (
                str(uuid.uuid4()), user_id, -PULSE_PRICE_PAISE, new_balance, f"pulse:{request_key}",
                json.dumps({"scan_id": scan_id, "handle": handle}, separators=(",", ":")), now.isoformat(),
            ),
        )
        return scan_id

    return await run_in_transaction(_reserve, mode="IMMEDIATE", operation_name="reserve Creator Pulse")


async def _refund_pulse(scan_id: str, request_key: str, error_code: str) -> None:
    async def _refund(db) -> None:
        cursor = await db.execute("SELECT * FROM creator_pulse_scans WHERE id=?", (scan_id,))
        row = await cursor.fetchone()
        if not row:
            return
        scan = dict(row)
        if scan.get("status") != "processing" or _safe_int(scan.get("charged_paise")) != PULSE_PRICE_PAISE:
            return
        user_id = str(scan["user_id"])
        wallet_cursor = await db.execute("SELECT balance_paise FROM creator_pulse_wallets WHERE user_id=?", (user_id,))
        wallet_row = await wallet_cursor.fetchone()
        balance = _safe_int(dict(wallet_row).get("balance_paise") if wallet_row else 0)
        new_balance = balance + PULSE_PRICE_PAISE
        now = utc_now().isoformat()
        await db.execute("UPDATE creator_pulse_wallets SET balance_paise=?,updated_at=? WHERE user_id=?", (new_balance, now, user_id))
        await db.execute(
            "UPDATE creator_pulse_scans SET status='failed',charged_paise=0,error_code=? WHERE id=?",
            (error_code[:80], scan_id),
        )
        await db.execute(
            """INSERT INTO creator_pulse_transactions(
                 id,user_id,kind,delta_paise,balance_after_paise,reference,metadata_json,created_at
               ) VALUES (?,?, 'pulse_refund',?,?,?,?,?)""",
            (
                str(uuid.uuid4()), user_id, PULSE_PRICE_PAISE, new_balance, f"refund:{request_key}",
                json.dumps({"scan_id": scan_id, "reason": error_code[:80]}, separators=(",", ":")), now,
            ),
        )

    await run_in_transaction(_refund, mode="IMMEDIATE", operation_name="refund failed Creator Pulse")


async def _previous_delta(user_id: str, channel_id: str, current_snapshot: dict[str, Any]) -> dict[str, Any]:
    previous = await fetch_one(
        """SELECT * FROM creator_pulse_scans
           WHERE user_id=? AND channel_id=? AND status='completed'
           ORDER BY captured_at DESC LIMIT 1""",
        (user_id, channel_id),
    )
    if not previous:
        return {"available": False, "previous_captured_at": None, "subscriber_change": None, "view_change": None, "video_count_change": None}
    channel = current_snapshot["channel"]
    current_subscribers = channel.get("subscribers")
    previous_subscribers = previous.get("subscriber_count")
    subscriber_change = None if current_subscribers is None or previous_subscribers is None else int(current_subscribers) - int(previous_subscribers)
    return {
        "available": True,
        "previous_captured_at": previous.get("captured_at"),
        "subscriber_change": subscriber_change,
        "view_change": int(channel["total_views"]) - _safe_int(previous.get("total_views")),
        "video_count_change": int(channel["video_count"]) - _safe_int(previous.get("video_count")),
    }


async def _finalize_pulse(scan_id: str, snapshot: dict[str, Any], delta: dict[str, Any], request_key: str) -> dict[str, Any]:
    captured_at = utc_now().isoformat()
    channel = snapshot["channel"]
    report = {
        "id": scan_id,
        "request_key": request_key,
        "captured_at": captured_at,
        "charged_paise": PULSE_PRICE_PAISE,
        "channel": channel,
        "recent": snapshot["recent"],
        "delta": delta,
        "insights": _build_insights(snapshot),
    }

    async def _finish(db) -> int:
        scan_cursor = await db.execute("SELECT status,charged_paise FROM creator_pulse_scans WHERE id=?", (scan_id,))
        scan_row = await scan_cursor.fetchone()
        scan_state = dict(scan_row) if scan_row else {}
        if scan_state.get("status") != "processing" or _safe_int(scan_state.get("charged_paise")) != PULSE_PRICE_PAISE:
            raise RuntimeError("Creator Pulse charge is no longer active; retry safely.")
        wallet_cursor = await db.execute("SELECT balance_paise FROM creator_pulse_wallets WHERE user_id=(SELECT user_id FROM creator_pulse_scans WHERE id=?)", (scan_id,))
        wallet_row = await wallet_cursor.fetchone()
        balance = _safe_int(dict(wallet_row).get("balance_paise") if wallet_row else 0)
        persisted = {**report, "balance_paise": balance}
        await db.execute(
            """UPDATE creator_pulse_scans SET
                 channel_id=?,channel_title=?,subscriber_count=?,total_views=?,video_count=?,status='completed',
                 snapshot_json=?,error_code=NULL,captured_at=? WHERE id=? AND status='processing'""",
            (
                channel["id"], channel["title"], channel.get("subscribers"), channel["total_views"], channel["video_count"],
                json.dumps(persisted, separators=(",", ":"), ensure_ascii=False), captured_at, scan_id,
            ),
        )
        return balance

    balance = await run_in_transaction(_finish, mode="IMMEDIATE", operation_name="finalize Creator Pulse")
    report["balance_paise"] = balance
    return report


@router.post("/creator-pulse/analyse")
async def creator_pulse_analyse(body: dict, user: dict = Depends(current_user)) -> dict[str, Any]:
    handle = _normalize_handle(body.get("handle"))
    request_key = _validate_request_key(body.get("request_key"))
    user_id = str(user["id"])
    if requires_verification_for_processing(user):
        raise HTTPException(403, "Verify your email before running Creator Pulse.")
    await _recover_stale_processing(user_id)
    existing = await fetch_one(
        "SELECT * FROM creator_pulse_scans WHERE user_id=? AND request_key=?",
        (user_id, request_key),
    )
    if existing:
        if existing.get("status") == "completed":
            return await _completed_scan_payload(existing)
        if existing.get("status") == "processing":
            raise HTTPException(409, "This Creator Pulse request is already running.")
        raise HTTPException(409, "That Creator Pulse request already failed and was refunded. Run a new Pulse.")
    if not _youtube_api_key():
        raise HTTPException(503, "Creator Pulse is not connected to YouTube yet.")

    async with _user_locks[user_id], distributed_advisory_lock(f"creator-pulse-charge:{user_id}"):
        try:
            scan_id = await _reserve_pulse(user_id, handle, request_key)
        except PulseBalanceInsufficient as exc:
            raise HTTPException(402, "Pulse Balance is below ₹1. Add ₹10, ₹20 or ₹50 to continue.") from exc
        except PulseDuplicate as exc:
            raise HTTPException(409, f"This Creator Pulse request is already {exc}.") from exc

    try:
        snapshot = await _fetch_youtube_snapshot(handle)
        delta = await _previous_delta(user_id, str(snapshot["channel"]["id"]), snapshot)
        report = await _finalize_pulse(scan_id, snapshot, delta, request_key)
        await _audit(
            user_id,
            "creator_pulse.completed",
            "creator_pulse_scan",
            scan_id,
            {"channel_id": snapshot["channel"]["id"], "handle": handle, "charged_paise": PULSE_PRICE_PAISE},
        )
        return report
    except PulseProviderError as exc:
        await _refund_pulse(scan_id, request_key, exc.code)
        await _audit(user_id, "creator_pulse.refunded", "creator_pulse_scan", scan_id, {"reason": exc.code})
        raise HTTPException(exc.status_code, str(exc)) from exc
    except HTTPException:
        await _refund_pulse(scan_id, request_key, "REQUEST_FAILED")
        raise
    except Exception as exc:
        await _refund_pulse(scan_id, request_key, "INTERNAL_FAILURE")
        await _audit(user_id, "creator_pulse.refunded", "creator_pulse_scan", scan_id, {"reason": "INTERNAL_FAILURE", "error_type": type(exc).__name__})
        raise HTTPException(500, "Creator Pulse could not finish safely. Your ₹1 was refunded.") from exc

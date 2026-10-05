from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.core.database import execute, fetch_all


PAID_SOURCE_RETENTION_DAYS = 30


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def source_media_expiry(user: dict[str, Any], *, at: datetime | None = None) -> datetime:
    """Return the retention deadline for a newly accepted source video.

    Free sources keep the existing short retention window. Paid plans retain
    source media for up to 30 days so an unused Short allowance cannot become
    stranded merely because the source disappeared the next day.

    Mini Pass is a fixed 30-day entitlement, so its source never outlives the
    pass itself. Recurring paid plans receive a rolling 30-day source window
    from each upload; access controls still decide what the user may do after a
    subscription later ends.
    """
    base = at or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    settings = get_settings()
    free_expiry = base + timedelta(hours=max(1, int(settings.file_expiry_hours)))
    plan = str(user.get("plan") or "free").strip().lower()
    if plan == "free":
        return free_expiry

    paid_expiry = base + timedelta(days=PAID_SOURCE_RETENTION_DAYS)
    if plan == "mini_pass":
        entitlement_end = _parse_iso(user.get("plan_expires_at"))
        if entitlement_end is None or entitlement_end <= base:
            return free_expiry
        return min(paid_expiry, entitlement_end.astimezone(timezone.utc))

    return paid_expiry


async def reconcile_active_paid_source_retention() -> int:
    """Extend still-retained paid sources created under the old 24-hour rule.

    Already-expired/deleted media is intentionally never resurrected. This only
    repairs rows whose source is still live when the new retention policy ships.
    """
    rows = await fetch_all(
        """SELECT v.id,v.created_at,v.expires_at,u.plan,u.plan_expires_at
           FROM videos v
           JOIN projects p ON p.id=v.project_id
           JOIN users u ON u.id=p.user_id
           WHERE v.status<>'expired' AND u.plan<>'free'"""
    )
    current_time = datetime.now(timezone.utc)
    updated = 0
    for row in rows:
        created = _parse_iso(row.get("created_at"))
        current_expiry = _parse_iso(row.get("expires_at"))
        if created is None or current_expiry is None:
            continue
        target = source_media_expiry(
            {"plan": row.get("plan"), "plan_expires_at": row.get("plan_expires_at")},
            at=created.astimezone(timezone.utc),
        )
        if target <= current_time or target <= current_expiry:
            continue
        await execute(
            "UPDATE videos SET expires_at=? WHERE id=? AND status<>'expired'",
            (target.isoformat(), row["id"]),
        )
        updated += 1
    return updated

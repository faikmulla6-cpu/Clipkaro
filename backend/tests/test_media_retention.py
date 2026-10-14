import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from app.core.config import get_settings
from app.services import media_retention
from app.services.media_retention import PAID_SOURCE_RETENTION_DAYS, source_media_expiry


BASE = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def test_free_source_keeps_short_default_retention(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "file_expiry_hours", 24)
    expiry = source_media_expiry({"plan": "free"}, at=BASE)
    assert expiry == BASE + timedelta(hours=24)


def test_paid_subscription_source_gets_rolling_thirty_days():
    expiry = source_media_expiry({"plan": "creator"}, at=BASE)
    assert expiry == BASE + timedelta(days=PAID_SOURCE_RETENTION_DAYS)


def test_mini_pass_source_never_outlives_pass():
    entitlement_end = BASE + timedelta(days=11)
    expiry = source_media_expiry(
        {"plan": "mini_pass", "plan_expires_at": entitlement_end.isoformat()},
        at=BASE,
    )
    assert expiry == entitlement_end


def test_fresh_mini_pass_source_is_capped_at_thirty_days():
    entitlement_end = BASE + timedelta(days=45)
    expiry = source_media_expiry(
        {"plan": "mini_pass", "plan_expires_at": entitlement_end.isoformat()},
        at=BASE,
    )
    assert expiry == BASE + timedelta(days=PAID_SOURCE_RETENTION_DAYS)


def test_expired_mini_pass_falls_back_to_free_retention(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "file_expiry_hours", 24)
    expiry = source_media_expiry(
        {"plan": "mini_pass", "plan_expires_at": (BASE - timedelta(minutes=1)).isoformat()},
        at=BASE,
    )
    assert expiry == BASE + timedelta(hours=24)


def test_reconcile_extends_only_live_paid_sources(monkeypatch):
    now = datetime.now(timezone.utc)
    created = now - timedelta(hours=2)
    old_expiry = created + timedelta(hours=24)
    fetch = AsyncMock(return_value=[
        {
            "id": "paid-source",
            "created_at": created.isoformat(),
            "expires_at": old_expiry.isoformat(),
            "plan": "creator",
            "plan_expires_at": (now + timedelta(days=20)).isoformat(),
        }
    ])
    execute = AsyncMock()
    monkeypatch.setattr(media_retention, "fetch_all", fetch)
    monkeypatch.setattr(media_retention, "execute", execute)

    updated = asyncio.run(media_retention.reconcile_active_paid_source_retention())

    assert updated == 1
    args = execute.await_args.args
    assert args[0].startswith("UPDATE videos SET expires_at=")
    assert args[1][1] == "paid-source"
    target = datetime.fromisoformat(args[1][0])
    assert target == created + timedelta(days=PAID_SOURCE_RETENTION_DAYS)

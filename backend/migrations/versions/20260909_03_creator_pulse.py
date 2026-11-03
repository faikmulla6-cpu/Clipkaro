"""Add Creator Pulse balance, checkout, ledger and snapshot tables.

Revision ID: 20260909_03
Revises: 20260830_02

Creator Pulse is deliberately isolated from subscription entitlements. Pulse
balance is prepaid, never auto-renews, and each successful analysis records an
immutable ₹1 ledger entry plus a YouTube snapshot. The migration is additive and
its downgrade is intentionally non-destructive.
"""

from alembic import op

revision = "20260909_03"
down_revision = "20260830_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS creator_pulse_wallets (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            balance_paise INTEGER NOT NULL DEFAULT 0 CHECK(balance_paise >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS creator_pulse_checkouts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_reference TEXT NOT NULL UNIQUE,
            amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
            status TEXT NOT NULL CHECK(status IN ('created','authorized','verified','failed','expired')),
            payment_id TEXT,
            created_at TEXT NOT NULL,
            verified_at TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_creator_pulse_checkouts_user
        ON creator_pulse_checkouts(user_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS creator_pulse_transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK(kind IN ('topup','pulse_charge','pulse_refund')),
            delta_paise INTEGER NOT NULL,
            balance_after_paise INTEGER NOT NULL CHECK(balance_after_paise >= 0),
            reference TEXT NOT NULL UNIQUE,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_creator_pulse_transactions_user
        ON creator_pulse_transactions(user_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS creator_pulse_scans (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            request_key TEXT NOT NULL,
            handle TEXT NOT NULL,
            channel_id TEXT,
            channel_title TEXT,
            subscriber_count INTEGER,
            total_views INTEGER NOT NULL DEFAULT 0,
            video_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL CHECK(status IN ('processing','completed','failed')),
            charged_paise INTEGER NOT NULL DEFAULT 0 CHECK(charged_paise >= 0),
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            error_code TEXT,
            captured_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, request_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_creator_pulse_scans_history
        ON creator_pulse_scans(user_id, channel_id, captured_at DESC)
        """
    )


def downgrade() -> None:
    # Pulse balance and paid analysis history are financial/user records. An
    # application rollback must never silently delete them.
    pass

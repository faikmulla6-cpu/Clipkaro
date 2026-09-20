"""Add Post Karo credentials, account links, revisioned drafts and publication history.

Revision ID: 20260920_04
Revises: 20260909_03

The migration is additive. Encrypted provider credentials and publishing history
are user records, so downgrade is intentionally non-destructive.
"""

from alembic import op

revision = "20260920_04"
down_revision = "20260909_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_karo_connections (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            api_key_ciphertext TEXT NOT NULL,
            api_key_masked TEXT NOT NULL,
            api_key_fingerprint TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            validated_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_karo_accounts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            platform TEXT NOT NULL CHECK(platform IN ('instagram','youtube')),
            provider_account_id TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            can_post INTEGER NOT NULL DEFAULT 1,
            connection_status TEXT NOT NULL DEFAULT 'connected',
            health_json TEXT NOT NULL DEFAULT '{}',
            last_synced_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, platform),
            UNIQUE(user_id, provider_account_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_karo_accounts_user
        ON post_karo_accounts(user_id, platform)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_karo_drafts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            export_id TEXT NOT NULL REFERENCES exports(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
            instagram_enabled INTEGER NOT NULL DEFAULT 0,
            instagram_caption TEXT NOT NULL DEFAULT '',
            instagram_hashtags TEXT NOT NULL DEFAULT '[]',
            youtube_enabled INTEGER NOT NULL DEFAULT 0,
            youtube_title TEXT NOT NULL DEFAULT '',
            youtube_description TEXT NOT NULL DEFAULT '',
            youtube_tags TEXT NOT NULL DEFAULT '[]',
            youtube_visibility TEXT NOT NULL DEFAULT 'public'
                CHECK(youtube_visibility IN ('public','unlisted','private')),
            scheduled_for TEXT,
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, export_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_karo_publications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            export_id TEXT NOT NULL REFERENCES exports(id) ON DELETE CASCADE,
            draft_id TEXT NOT NULL REFERENCES post_karo_drafts(id) ON DELETE CASCADE,
            draft_revision INTEGER NOT NULL CHECK(draft_revision > 0),
            request_id TEXT NOT NULL,
            job_id TEXT,
            mode TEXT NOT NULL CHECK(mode IN ('now','schedule')),
            status TEXT NOT NULL
                CHECK(status IN ('queued','processing','scheduled','published','partial','failed')),
            snapshot_json TEXT NOT NULL,
            provider_post_id TEXT,
            platform_results_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            scheduled_for TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, request_id),
            UNIQUE(draft_id, draft_revision)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_karo_publications_user
        ON post_karo_publications(user_id, created_at DESC)
        """
    )


def downgrade() -> None:
    # Never silently delete encrypted connection state, drafts or publication history.
    pass

"""Add BYOK credentials and cartoon projects.

Revision ID: 20261119_13
Revises: 20261024_12
"""
from alembic import op

revision = "20261119_13"
down_revision = "20261024_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cartoon_studio_access_override BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cartoon_provider_credentials (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL CHECK(provider IN ('openrouter')),
            api_key_ciphertext TEXT NOT NULL,
            api_key_masked TEXT NOT NULL,
            api_key_fingerprint TEXT NOT NULL,
            validated_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cartoon_projects (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL CHECK(duration_seconds BETWEEN 15 AND 60),
            aspect_ratio TEXT NOT NULL CHECK(aspect_ratio IN ('9:16','16:9','1:1')),
            style TEXT NOT NULL,
            language TEXT NOT NULL,
            text_model TEXT NOT NULL,
            tts_model TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued'
              CHECK(status IN ('queued','processing','ready','failed')),
            progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
            stage TEXT NOT NULL DEFAULT 'queued',
            storyboard_json TEXT NOT NULL DEFAULT '{}',
            assets_json TEXT NOT NULL DEFAULT '{}',
            reference_key TEXT,
            reference_generation TEXT,
            output_key TEXT,
            output_generation TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cartoon_projects_user_created "
        "ON cartoon_projects(user_id, created_at DESC)"
    )


def downgrade() -> None:
    # Keep customer-created videos and encrypted credentials; downgrade is non-destructive.
    pass

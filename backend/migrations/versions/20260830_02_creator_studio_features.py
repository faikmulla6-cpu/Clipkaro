"""Add Creator Studio feature tables to existing production databases.

Revision ID: 20260830_02
Revises: 20260817_01

The Content Pack and Smart Transcript Review tables were added to the original
baseline after production databases had already applied that revision. Fresh
databases therefore had the tables, while upgraded databases did not. This
forward, idempotent migration closes that gap without modifying existing rows.
"""

from alembic import op

revision = "20260830_02"
down_revision = "20260817_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS transcript_corrections (
            id TEXT PRIMARY KEY,
            transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            segment_index INTEGER NOT NULL,
            segment_key TEXT NOT NULL,
            original_text TEXT NOT NULL,
            corrected_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'corrected',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(transcript_id, segment_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transcript_corrections_project
        ON transcript_corrections(project_id, updated_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS content_packs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            provider TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_content_packs_project
        ON content_packs(project_id)
        """
    )


def downgrade() -> None:
    # Intentionally non-destructive. These tables can contain creator-authored
    # corrections and generated publishing assets, so an application rollback
    # must not silently delete user data.
    pass

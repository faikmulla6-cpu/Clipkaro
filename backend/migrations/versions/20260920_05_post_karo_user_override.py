"""Add a narrowly scoped per-user Post Karo access override.

Revision ID: 20260920_05
Revises: 20260920_04

The override defaults off for every user. It exists only to grant Post Karo
without changing billing plan, role, quota or any other entitlement.
"""

from alembic import op


revision = "20260920_05"
down_revision = "20260920_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS post_karo_access_override BOOLEAN NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    # Preserve explicit per-user access state on rollback rather than silently
    # removing an administrative entitlement record.
    pass

"""Persist non-destructive Smart Edit plans on clips.

Revision ID: 20261004_06
Revises: 20260920_05
"""

from alembic import op

revision = "20261004_06"
down_revision = "20260920_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS clip_edit_plans (
        clip_id TEXT PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,
        plan_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL
        )"""
    )


def downgrade() -> None:
    # Non-destructive rollback: creator edit decisions are retained.
    pass

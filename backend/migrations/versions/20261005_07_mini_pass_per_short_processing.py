"""Align Mini Pass processing with 5 Shorts x 25 source minutes.

Revision ID: 20261005_07
Revises: 20261004_06
"""

from alembic import op

revision = "20261005_07"
down_revision = "20261004_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION clipkaro_minute_limit(plan_name TEXT)
        RETURNS DOUBLE PRECISION
        LANGUAGE SQL
        IMMUTABLE
        AS $$
          SELECT CASE plan_name
            WHEN 'mini_pass' THEN 125
            WHEN 'creator' THEN 60
            WHEN 'growth' THEN 180
            WHEN 'pro' THEN 480
            WHEN 'agency' THEN 1500
            ELSE 15
          END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION clipkaro_minute_limit(plan_name TEXT)
        RETURNS DOUBLE PRECISION
        LANGUAGE SQL
        IMMUTABLE
        AS $$
          SELECT CASE plan_name
            WHEN 'mini_pass' THEN 25
            WHEN 'creator' THEN 60
            WHEN 'growth' THEN 180
            WHEN 'pro' THEN 480
            WHEN 'agency' THEN 1500
            ELSE 15
          END
        $$;
        """
    )

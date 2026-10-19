"""Expand Creator/Growth/Pro minute ledger to per-video entitlements.

Revision ID: 20261019_09
Revises: 20261006_08

Each source still consumes one Short credit, with a strict per-source limit
enforced by the media pipeline. The period ledger cap equals the maximum
possible usage across all included Short credits. Mini Pass/Free/Agency
retain their previously published rules.
"""
from alembic import op

revision = "20261019_09"
down_revision = "20261006_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION clipkaro_minute_limit(plan_name TEXT)
        RETURNS DOUBLE PRECISION LANGUAGE SQL IMMUTABLE
        AS $$
          SELECT CASE plan_name
            WHEN 'mini_pass' THEN 125
            WHEN 'creator' THEN 900
            WHEN 'growth' THEN 9000
            WHEN 'pro' THEN 72000
            WHEN 'agency' THEN 1500
            ELSE 15
          END
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION clipkaro_minute_limit(plan_name TEXT)
        RETURNS DOUBLE PRECISION LANGUAGE SQL IMMUTABLE
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
    """)

"""Independent Real Smart Layout billing ledger. No changes to Karo Minutes."""
from alembic import op

revision = "20261024_12"
down_revision = "20261021_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE IF NOT EXISTS smart_layout_credit_periods(
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        period_key TEXT NOT NULL, plan_key TEXT NOT NULL,
        allowance INTEGER NOT NULL CHECK(allowance>=0),
        daily_cap INTEGER NOT NULL CHECK(daily_cap>=0),
        policy_version TEXT NOT NULL, period_end TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id,period_key)
      );
      CREATE TABLE IF NOT EXISTS smart_layout_credit_reservations(
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64),
        period_key TEXT NOT NULL, credits INTEGER NOT NULL
          CHECK(credits BETWEEN 1 AND 3),
        status TEXT NOT NULL
          CHECK(status IN ('reserved','finalized','released')),
        job_id TEXT, reserved_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(user_id,fingerprint)
      );
      CREATE INDEX IF NOT EXISTS idx_smart_credit_period
        ON smart_layout_credit_reservations(user_id,period_key,status);
      CREATE INDEX IF NOT EXISTS idx_smart_credit_daily
        ON smart_layout_credit_reservations(user_id,reserved_at,status);
      CREATE INDEX IF NOT EXISTS idx_smart_credit_job
        ON smart_layout_credit_reservations(job_id);
    """)


def downgrade() -> None:
    # Production rollback must preserve paid usage evidence.
    # The feature flag disables new reservations without destructive SQL.
    pass

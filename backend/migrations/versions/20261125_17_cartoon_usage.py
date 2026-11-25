"""Track Cartoon Studio usage by purchase or subscription period."""
from alembic import op

revision = "20261125_17"
down_revision = "20261125_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cartoon_projects ADD COLUMN usage_period_key TEXT")
    op.execute(
        "CREATE INDEX idx_cartoon_projects_usage ON cartoon_projects(user_id, usage_period_key) "
        "WHERE usage_period_key IS NOT NULL"
    )
    op.execute("""
        CREATE TABLE cartoon_usage_refills (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            period_key TEXT NOT NULL,
            granted_seconds INTEGER NOT NULL CHECK(granted_seconds > 0),
            claimed_at TEXT NOT NULL,
            PRIMARY KEY(user_id, period_key)
        )
    """)


def downgrade() -> None:
    # Preserve the usage record and claims across application rollback.
    pass

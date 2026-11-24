"""Allow NVIDIA keys in the encrypted Cartoon Studio credential store."""
from alembic import op

revision = "20261122_15"
down_revision = "20261121_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE cartoon_provider_credentials "
        "DROP CONSTRAINT IF EXISTS cartoon_provider_credentials_provider_check"
    )
    op.execute(
        "ALTER TABLE cartoon_provider_credentials "
        "ADD CONSTRAINT cartoon_provider_credentials_provider_check "
        "CHECK(provider IN ('openrouter','nvidia'))"
    )


def downgrade() -> None:
    # The previous application works with the wider constraint. Keep saved keys.
    pass

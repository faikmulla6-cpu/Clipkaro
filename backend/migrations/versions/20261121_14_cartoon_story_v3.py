"""Allow portrait 4:5 cartoons without changing existing project data."""
from alembic import op
revision = "20261121_14"
down_revision = "20261119_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cartoon_projects DROP CONSTRAINT IF EXISTS cartoon_projects_aspect_ratio_check")
    op.execute("ALTER TABLE cartoon_projects ADD CONSTRAINT cartoon_projects_aspect_ratio_check CHECK(aspect_ratio IN ('9:16','16:9','1:1','4:5'))")


def downgrade() -> None:
    # Preserve customer 4:5 projects on application rollback.
    pass

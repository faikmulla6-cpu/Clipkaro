"""Allow Post Karo drafts and publications to use finished Cartoon Studio projects."""
from alembic import op

revision = "20261125_16"
down_revision = "20261122_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE post_karo_drafts
          ALTER COLUMN export_id DROP NOT NULL,
          ADD COLUMN cartoon_project_id TEXT REFERENCES cartoon_projects(id) ON DELETE CASCADE,
          ADD COLUMN youtube_audience TEXT CHECK(youtube_audience IN ('kids','general')),
          ADD UNIQUE(user_id,cartoon_project_id),
          ADD CHECK((export_id IS NULL) <> (cartoon_project_id IS NULL))
    """)
    op.execute("ALTER TABLE post_karo_publications ALTER COLUMN export_id DROP NOT NULL")


def downgrade() -> None:
    # Keep cartoon drafts and publication history if application code is rolled back.
    pass

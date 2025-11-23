"""add team_id to extractor_jobs"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_team_id_to_extractor_jobs"
down_revision = "0002_add_team_id_to_bulk_jobs"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "extractor_jobs",
        sa.Column("team_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_extractor_jobs_team_id",
        "extractor_jobs",
        ["team_id"]
    )

def downgrade():
    op.drop_index("ix_extractor_jobs_team_id", table_name="extractor_jobs")
    op.drop_column("extractor_jobs", "team_id")

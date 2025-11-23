
"""add team_id to bulk_jobs"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_team_id_to_bulk_jobs"
down_revision = "0001_add_job_id_to_credit_reservations"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "bulk_jobs",
        sa.Column("team_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_bulk_jobs_team_id",
        "bulk_jobs",
        ["team_id"]
    )

def downgrade():
    op.drop_index("ix_bulk_jobs_team_id", table_name="bulk_jobs")
    op.drop_column("bulk_jobs", "team_id")

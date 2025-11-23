
# 0006_bulkjob_team_output.py

from alembic import op
import sqlalchemy as sa

revision = "0006_bulkjob_team_output"
down_revision = "0005_create_team_tables"

def upgrade():
    op.add_column("bulk_jobs", sa.Column("team_id", sa.Integer, nullable=True))
    op.add_column("bulk_jobs", sa.Column("output_path", sa.String(500), nullable=True))

def downgrade():
    op.drop_column("bulk_jobs", "output_path")
    op.drop_column("bulk_jobs", "team_id")

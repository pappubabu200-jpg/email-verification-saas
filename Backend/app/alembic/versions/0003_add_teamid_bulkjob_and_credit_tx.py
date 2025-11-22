# backend/app/alembic/versions/0003_add_teamid_bulkjob_and_credit_tx.py
from alembic import op
import sqlalchemy as sa

revision = '0003_add_teamid_bulkjob_and_credit_tx'
down_revision = '0002_create_teams_and_teamid_bulkjob'
branch_labels = None
depends_on = None

def upgrade():
    # Add team_id to credit transactions
    op.add_column("credit_transactions", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_index("ix_credit_transactions_team_id", "credit_transactions", ["team_id"])

    # Ensure bulk_jobs.team_id exists (if not already)
    op.add_column("bulk_jobs", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_index("ix_bulk_jobs_team_id", "bulk_jobs", ["team_id"])

def downgrade():
    op.drop_index("ix_credit_transactions_team_id", table_name="credit_transactions")
    op.drop_column("credit_transactions", "team_id")

    op.drop_index("ix_bulk_jobs_team_id", table_name="bulk_jobs")
    op.drop_column("bulk_jobs", "team_id")

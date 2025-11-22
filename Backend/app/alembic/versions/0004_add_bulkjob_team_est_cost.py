
# backend/app/alembic/versions/000X_add_bulkjob_team_est_cost.py
"""add bulk_jobs team_id and estimated_cost

Revision ID: add_bulk_job_team_est_cost
Revises: 0001_initial
Create Date: 2025-11-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_bulk_job_team_est_cost'
down_revision = None  # replace with your current down_revision id
branch_labels = None
depends_on = None

def upgrade():
    # add team_id (nullable) and estimated_cost
    op.add_column('bulk_jobs', sa.Column('team_id', sa.Integer(), nullable=True))
    op.add_column('bulk_jobs', sa.Column('estimated_cost', sa.Numeric(18,6), nullable=True))
    # optionally add index on team_id
    op.create_index(op.f('ix_bulk_jobs_team_id'), 'bulk_jobs', ['team_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_bulk_jobs_team_id'), table_name='bulk_jobs')
    op.drop_column('bulk_jobs', 'estimated_cost')
    op.drop_column('bulk_jobs', 'team_id')

"""add bulk_jobs team_id and estimated_cost

Revision ID: 20251122_add_bulkjob_team_est_cost
Revises: 0001_initial
Create Date: 2025-11-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251122_add_bulkjob_team_est_cost'
down_revision = '0001_initial'   # <-- change this if your current head is different
branch_labels = None
depends_on = None


def upgrade():
    # NOTE: guard checks are intentionally minimal — Alembic will error if column exists.
    # Add team_id column
    op.add_column('bulk_jobs', sa.Column('team_id', sa.Integer(), nullable=True))
    # Add estimated_cost column
    op.add_column('bulk_jobs', sa.Column('estimated_cost', sa.Numeric(18,6), nullable=True))
    # Create index for team_id
    op.create_index(op.f('ix_bulk_jobs_team_id'), 'bulk_jobs', ['team_id'], unique=False)


def downgrade():
    # Drop index then columns (reverse)
    try:
        op.drop_index(op.f('ix_bulk_jobs_team_id'), table_name='bulk_jobs')
    except Exception:
        # ignore if index missing
        pass
    try:
        op.drop_column('bulk_jobs', 'estimated_cost')
    except Exception:
        pass
    try:
        op.drop_column('bulk_jobs', 'team_id')
    except Exception:
        pass




"""add teams, team_members, team columns, user billing fields, bulk_job.team_id

Revision ID: 20251122_add_teams_and_billing
Revises: 
Create Date: 2025-11-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = '20251122_add_teams_and_billing'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # users: add stripe_customer_id, credits
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('credits', sa.Numeric(18,6), nullable=True, server_default='0'))

    # teams
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False, unique=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('credits', sa.Numeric(18,6), nullable=True, server_default='0'),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    # team_members
    op.create_table(
        'team_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(length=50), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now()),
    )

    # bulk_jobs: add team_id (nullable)
    with op.batch_alter_table('bulk_jobs', schema=None) as batch_op:
        try:
            batch_op.add_column(sa.Column('team_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_bulkjob_team', 'teams', ['team_id'], ['id'])
        except Exception:
            # if bulk_jobs table missing in some projects, ignore
            pass

    # credit_reservations: add job_id column if missing (to link reservation->job)
    with op.batch_alter_table('credit_reservations', schema=None) as batch_op:
        try:
            batch_op.add_column(sa.Column('job_id', sa.String(length=128), nullable=True))
        except Exception:
            pass


def downgrade():
    # drop columns and tables in reverse order
    with op.batch_alter_table('credit_reservations', schema=None) as batch_op:
        try:
            batch_op.drop_column('job_id')
        except Exception:
            pass

    with op.batch_alter_table('bulk_jobs', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('fk_bulkjob_team', type_='foreignkey')
            batch_op.drop_column('team_id')
        except Exception:
            pass

    op.drop_table('team_members')
    op.drop_table('teams')

    with op.batch_alter_table('users', schema=None) as batch_op:
        try:
            batch_op.drop_column('credits')
            batch_op.drop_column('stripe_customer_id')
        except Exception:
            pass

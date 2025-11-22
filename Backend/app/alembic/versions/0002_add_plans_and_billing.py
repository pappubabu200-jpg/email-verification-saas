# backend/app/alembic/versions/0002_add_plans_and_billing.py
"""add plans table, user.plan, user.credits, bulk_job.team_id, bulk_job.estimated_cost, credit_reservation.job_id

Revision ID: 0002_add_plans_and_billing
Revises: 0001_initial
Create Date: 2025-11-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_plans_and_billing'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    # plans table
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('monthly_price_usd', sa.Numeric(10,2), nullable=False, server_default='0'),
        sa.Column('daily_search_limit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('monthly_credit_allowance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rate_limit_per_sec', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

    # add user.plan and user.credits
    op.add_column('users', sa.Column('plan', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('credits', sa.Numeric(18,6), nullable=True, server_default='0'))

    # add team tables (if not present)
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('credits', sa.Numeric(18,6), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

    op.create_table(
        'team_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.String(50), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

    # bulk_job changes: team_id, estimated_cost
    with op.batch_alter_table('bulk_job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('team_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('estimated_cost', sa.Numeric(18,6), nullable=True))

    # credit_reservation: add job_id
    with op.batch_alter_table('credit_reservations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job_id', sa.String(128), nullable=True))

def downgrade():
    with op.batch_alter_table('credit_reservations') as batch_op:
        batch_op.drop_column('job_id')
    with op.batch_alter_table('bulk_job') as batch_op:
        batch_op.drop_column('estimated_cost')
        batch_op.drop_column('team_id')
    op.drop_table('team_members')
    op.drop_table('teams')
    op.drop_column('users', 'credits')
    op.drop_column('users', 'plan')
    op.drop_table('plans')

"""add teams, team_members and credit_reservation.team_id

Revision ID: 20251122_add_teams_and_team_reservations
Revises: 20251122_add_bulkjob_team_est_cost
Create Date: 2025-11-22 00:00:00.000001
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251122_add_teams_and_team_reservations'
down_revision = '20251122_add_bulkjob_team_est_cost'
branch_labels = None
depends_on = None

def upgrade():
    # teams table
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False, unique=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('credits', sa.Numeric(18,6), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    # team_members table
    op.create_table(
        'team_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )

    # add team_id to credit_reservations (nullable)
    op.add_column('credit_reservations', sa.Column('team_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_credit_reservations_team_id'), 'credit_reservations', ['team_id'], unique=False)


def downgrade():
    try:
        op.drop_index(op.f('ix_credit_reservations_team_id'), table_name='credit_reservations')
    except Exception:
        pass
    try:
        op.drop_column('credit_reservations', 'team_id')
    except Exception:
        pass
    try:
        op.drop_table('team_members')
    except Exception:
        pass
    try:
        op.drop_table('teams')
    except Exception:
        pass

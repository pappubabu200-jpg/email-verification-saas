"""add plans and webhook_events tables

Revision ID: 0002_add_plans_and_webhook_events
Revises: 0001_initial
Create Date: 2025-11-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_plans_and_webhook_events'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(length=200), nullable=False),
        sa.Column('monthly_price_usd', sa.Numeric(10, 2), nullable=True, server_default="0"),
        sa.Column('daily_search_limit', sa.Integer(), nullable=True, server_default="0"),
        sa.Column('monthly_credit_allowance', sa.Integer(), nullable=True, server_default="0"),
        sa.Column('rate_limit_per_sec', sa.Integer(), nullable=True, server_default="0"),
        sa.Column('is_public', sa.Boolean(), nullable=True, server_default=sa.sql.expression.true()),
    )

    op.create_table(
        'webhook_events',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('event_type', sa.String(length=200), nullable=True),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade():
    op.drop_table('webhook_events')
    op.drop_table('plans')

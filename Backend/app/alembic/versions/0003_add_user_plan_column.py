"""add plan column to users

Revision ID: 0003_add_user_plan_column
Revises: 0002_add_plans_and_webhook_events
Create Date: 2025-11-24 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_add_user_plan_column'
down_revision = '0002_add_plans_and_webhook_events'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('plan', sa.String(length=100), nullable=True))

def downgrade():
    op.drop_column('users', 'plan')

"""add credits numeric column to users"""

from alembic import op
import sqlalchemy as sa

revision = "0005_add_credits_to_users"
down_revision = "0004_add_plan_to_users"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "users",
        sa.Column("credits", sa.Numeric(18, 6), server_default="0", nullable=False)
    )

def downgrade():
    op.drop_column("users", "credits")

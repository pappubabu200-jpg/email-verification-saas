"""add plan column to users"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_plan_to_users"
down_revision = "0003_add_team_id_to_extractor_jobs"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "users",
        sa.Column("plan", sa.String(100), nullable=True)
    )
    op.create_index(
        "ix_users_plan",
        "users",
        ["plan"]
    )

def downgrade():
    op.drop_index("ix_users_plan", table_name="users")
    op.drop_column("users", "plan")

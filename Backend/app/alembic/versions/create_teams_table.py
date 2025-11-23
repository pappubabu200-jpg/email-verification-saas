"""create teams table"""

from alembic import op
import sqlalchemy as sa

revision = "0006_create_teams"
down_revision = "0005_add_credits_to_users"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("credits", sa.Numeric(18, 6), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_teams_owner_id", "teams", ["owner_id"])

def downgrade():
    op.drop_index("ix_teams_owner_id", table_name="teams")
    op.drop_table("teams")

from alembic import op
import sqlalchemy as sa

revision = "0005_create_team_tables"
down_revision = "0004_create_credit_reservations"

def upgrade():
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("credits", sa.Numeric(20, 6), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id")),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("role", sa.String(50), default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("team_members")
    op.drop_table("teams")

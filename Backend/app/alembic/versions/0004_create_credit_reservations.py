from alembic import op
import sqlalchemy as sa

revision = "0004_create_credit_reservations"
down_revision = "0003_add_user_credits"

def upgrade():
    op.create_table(
        "credit_reservations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("team_id", sa.Integer, nullable=True),
        sa.Column("amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("locked", sa.Boolean, default=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reference", sa.String(255), nullable=True),
    )

def downgrade():
    op.drop_table("credit_reservations")

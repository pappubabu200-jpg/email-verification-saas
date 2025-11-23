from alembic import op
import sqlalchemy as sa

revision = "0002_add_plans_and_user_plan"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("monthly_price_usd", sa.Numeric(10, 2), default=0),
        sa.Column("daily_search_limit", sa.Integer, default=0),
        sa.Column("monthly_credit_allowance", sa.Integer, default=0),
        sa.Column("rate_limit_per_sec", sa.Integer, default=0),
        sa.Column("is_public", sa.Boolean, default=True),
    )

    op.add_column("users", sa.Column("plan", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("users", "plan")
    op.drop_table("plans")

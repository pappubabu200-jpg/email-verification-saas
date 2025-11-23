"""add subscriptions table"""

from alembic import op
import sqlalchemy as sa

revision = "20250101_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.Column("stripe_subscription_id", sa.String(255), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),

        sa.Column("plan_name", sa.String(100)),
        sa.Column("price_amount", sa.Numeric(10, 2)),
        sa.Column("price_interval", sa.String(20)),

        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean, server_default="false"),

        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),

        sa.Column("raw", sa.Text),
    )

    op.create_index("idx_subscriptions_stripe_sub_id", "subscriptions", ["stripe_subscription_id"])
    op.create_index("idx_subscriptions_status", "subscriptions", ["status"])


def downgrade():
    op.drop_table("subscriptions")

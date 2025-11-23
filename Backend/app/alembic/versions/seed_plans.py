"""seed default plans"""

from alembic import op
import sqlalchemy as sa

revision = "0009_seed_plans"
down_revision = "0008_performance_indexes"
branch_labels = None
depends_on = None

def upgrade():
    plans = [
        ("free", "Free", 0, 20, 0, 1),
        ("pro", "Pro", 29, 200, 10000, 5),
        ("team", "Team", 199, 2000, 100000, 10),
        ("enterprise", "Enterprise", 0, 0, 0, 0),
    ]

    for p in plans:
        op.execute(
            f"""
            INSERT INTO plans (name, display_name, monthly_price_usd, daily_search_limit,
            monthly_credit_allowance, rate_limit_per_sec)
            VALUES ('{p[0]}','{p[1]}',{p[2]},{p[3]},{p[4]},{p[5]})
            ON CONFLICT (name) DO NOTHING;
            """
        )

def downgrade():
    op.execute("DELETE FROM plans;")

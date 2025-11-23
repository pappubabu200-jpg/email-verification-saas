"""performance indexes"""

from alembic import op

revision = "0008_performance_indexes"
down_revision = "0007_create_team_members"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_credit_tx_user_id", "credit_transactions", ["user_id"])
    op.create_index("ix_credit_reserve_user_id", "credit_reservations", ["user_id"])
    op.create_index("ix_bulk_jobs_user_id", "bulk_jobs", ["user_id"])

def downgrade():
    op.drop_index("ix_bulk_jobs_user_id", table_name="bulk_jobs")
    op.drop_index("ix_credit_reserve_user_id", table_name="credit_reservations")
    op.drop_index("ix_credit_tx_user_id", table_name="credit_transactions")

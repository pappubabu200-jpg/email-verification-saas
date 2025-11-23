"""add job_id to credit_reservations"""

from alembic import op
import sqlalchemy as sa

revision = "0001_add_job_id_to_credit_reservations"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "credit_reservations",
        sa.Column("job_id", sa.String(128), nullable=True)
    )
    op.create_index(
        "ix_credit_reservations_job_id",
        "credit_reservations",
        ["job_id"]
    )

def downgrade():
    op.drop_index("ix_credit_reservations_job_id", table_name="credit_reservations")
    op.drop_column("credit_reservations", "job_id")


## 0007_create_usage_logs.py

from alembic import op
import sqlalchemy as sa

revision = "0007_create_usage_logs"
down_revision = "0006_bulkjob_team_output"

def upgrade():
    op.create_table(
        "usage_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("api_key_id", sa.Integer, sa.ForeignKey("api_keys.id")),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("ip", sa.String(100)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("usage_logs")

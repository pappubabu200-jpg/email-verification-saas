
from alembic import op
import sqlalchemy as sa

revision = "0003_add_user_credits"
down_revision = "0002_add_plans_and_user_plan"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("credits", sa.Numeric(20, 6), server_default="0"))

def downgrade():
    op.drop_column("users", "credits")

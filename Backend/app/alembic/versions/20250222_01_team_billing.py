
"""add team billing tables + BulkJob.team_id

Revision ID: team_billing_001
Revises: <PUT_PREVIOUS_REVISION_HERE>
Create Date: 2025-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = 'team_billing_001'
down_revision = '<PUT_PREVIOUS_REVISION_HERE>'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------
    # TEAMS
    # ------------------------------
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("credits", sa.Numeric(18,6), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # ------------------------------
    # TEAM MEMBERS
    # ------------------------------
    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="member"),
        sa.Column("can_billing", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ------------------------------
    # TEAM TRANSACTIONS
    # ------------------------------
    op.create_table(
        "team_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18,6), nullable=False),
        sa.Column("balance_after", sa.Numeric(18,6), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("reference", sa.String(255)),
        sa.Column("metadata", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ------------------------------
    # ADD team_id COLUMN TO BulkJob
    # ------------------------------
    op.add_column("bulk_jobs", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_bulkjob_team",
        "bulk_jobs",
        "teams",
        ["team_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_bulkjob_team", "bulk_jobs", type_="foreignkey")
    op.drop_column("bulk_jobs", "team_id")
    op.drop_table("team_transactions")
    op.drop_table("team_members")
    op.drop_table("teams")

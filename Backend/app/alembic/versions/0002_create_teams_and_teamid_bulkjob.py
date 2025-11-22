# backend/app/alembic/versions/0002_create_teams_and_teamid_bulkjob.py
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_create_teams_and_teamid_bulkjob'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    # create teams table
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('credits', sa.Numeric(18,6), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index(op.f('ix_teams_owner_id'), 'teams', ['owner_id'], unique=False)

    # create team_members table
    op.create_table(
        'team_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index(op.f('ix_team_members_team_id'), 'team_members', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_members_user_id'), 'team_members', ['user_id'], unique=False)

    # add team_id column to bulk_job (nullable)
    op.add_column('bulk_jobs', sa.Column('team_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_bulk_jobs_team_id'), 'bulk_jobs', ['team_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_bulk_jobs_team_id'), table_name='bulk_jobs')
    op.drop_column('bulk_jobs', 'team_id')

    op.drop_index(op.f('ix_team_members_user_id'), table_name='team_members')
    op.drop_index(op.f('ix_team_members_team_id'), table_name='team_members')
    op.drop_table('team_members')

    op.drop_index(op.f('ix_teams_owner_id'), table_name='teams')
    op.drop_table('teams')

# backend/app/alembic/versions/0002_create_teams_and_teamid_bulkjob.py
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_create_teams_and_teamid_bulkjob'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    # create teams table
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('credits', sa.Numeric(18,6), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index(op.f('ix_teams_owner_id'), 'teams', ['owner_id'], unique=False)

    # create team_members table
    op.create_table(
        'team_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index(op.f('ix_team_members_team_id'), 'team_members', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_members_user_id'), 'team_members', ['user_id'], unique=False)

    # add team_id column to bulk_jobs (nullable)
    # adjust table name if your BulkJob model uses a different __tablename__
    op.add_column('bulk_jobs', sa.Column('team_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_bulk_jobs_team_id'), 'bulk_jobs', ['team_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_bulk_jobs_team_id'), table_name='bulk_jobs')
    op.drop_column('bulk_jobs', 'team_id')

    op.drop_index(op.f('ix_team_members_user_id'), table_name='team_members')
    op.drop_index(op.f('ix_team_members_team_id'), table_name='team_members')
    op.drop_table('team_members')

    op.drop_index(op.f('ix_teams_owner_id'), table_name='teams')
    op.drop_table('teams')

"""add_research_tables

Revision ID: 6435784a8f93
Revises: 640b0c57d4e0
Create Date: 2026-09-21 20:37:19.237497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6435784a8f93'
down_revision: Union[str, Sequence[str], None] = '640b0c57d4e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('scheduled_research_tasks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('task_type', sa.String(length=100), nullable=False),
    sa.Column('schedule', sa.String(length=100), nullable=False),
    sa.Column('enabled', sa.Integer(), nullable=False),
    sa.Column('last_run', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_run', sa.DateTime(timezone=True), nullable=True),
    sa.Column('run_count', sa.Integer(), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scheduled_research_tasks_enabled'), 'scheduled_research_tasks', ['enabled'], unique=False)
    op.create_index(op.f('ix_scheduled_research_tasks_name'), 'scheduled_research_tasks', ['name'], unique=False)
    op.create_index(op.f('ix_scheduled_research_tasks_next_run'), 'scheduled_research_tasks', ['next_run'], unique=False)
    op.create_index(op.f('ix_scheduled_research_tasks_task_type'), 'scheduled_research_tasks', ['task_type'], unique=False)
    
    op.create_table('research_task_executions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('task_type', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('findings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('insights_generated', sa.Integer(), nullable=False),
    sa.Column('contradictions_found', sa.Integer(), nullable=False),
    sa.Column('hypotheses_generated', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['task_id'], ['scheduled_research_tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_research_task_executions_status'), 'research_task_executions', ['status'], unique=False)
    op.create_index(op.f('ix_research_task_executions_task_id'), 'research_task_executions', ['task_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_research_task_executions_task_id'), table_name='research_task_executions')
    op.drop_index(op.f('ix_research_task_executions_status'), table_name='research_task_executions')
    op.drop_table('research_task_executions')
    op.drop_index(op.f('ix_scheduled_research_tasks_task_type'), table_name='scheduled_research_tasks')
    op.drop_index(op.f('ix_scheduled_research_tasks_next_run'), table_name='scheduled_research_tasks')
    op.drop_index(op.f('ix_scheduled_research_tasks_name'), table_name='scheduled_research_tasks')
    op.drop_index(op.f('ix_scheduled_research_tasks_enabled'), table_name='scheduled_research_tasks')
    op.drop_table('scheduled_research_tasks')

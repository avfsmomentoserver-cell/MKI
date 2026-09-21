"""add_documentation_tables

Revision ID: 640b0c57d4e0
Revises: 3efd7b1a065c
Create Date: 2026-09-21 20:31:16.866710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '640b0c57d4e0'
down_revision: Union[str, Sequence[str], None] = '3efd7b1a065c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('generated_documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('doc_type', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('source_ko_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('author', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('previous_version_id', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['previous_version_id'], ['generated_documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_generated_documents_created_at'), 'generated_documents', ['created_at'], unique=False)
    op.create_index(op.f('ix_generated_documents_doc_type'), 'generated_documents', ['doc_type'], unique=False)
    op.create_index(op.f('ix_generated_documents_title'), 'generated_documents', ['title'], unique=False)
    op.create_index(op.f('ix_generated_documents_type_version'), 'generated_documents', ['doc_type', 'version'], unique=False)
    
    op.create_table('document_update_triggers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('trigger_reason', sa.String(length=500), nullable=False),
    sa.Column('source_ko_id', sa.Uuid(), nullable=True),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processed', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['generated_documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_update_triggers_document_id'), 'document_update_triggers', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_update_triggers_processed'), 'document_update_triggers', ['processed'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_document_update_triggers_processed'), table_name='document_update_triggers')
    op.drop_index(op.f('ix_document_update_triggers_document_id'), table_name='document_update_triggers')
    op.drop_table('document_update_triggers')
    op.drop_index(op.f('ix_generated_documents_type_version'), table_name='generated_documents')
    op.drop_index(op.f('ix_generated_documents_title'), table_name='generated_documents')
    op.drop_index(op.f('ix_generated_documents_doc_type'), table_name='generated_documents')
    op.drop_index(op.f('ix_generated_documents_created_at'), table_name='generated_documents')
    op.drop_table('generated_documents')

"""add_book_tables

Revision ID: 827441a0fd4e
Revises: 6435784a8f93
Create Date: 2026-09-21 20:50:32.018505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '827441a0fd4e'
down_revision: Union[str, Sequence[str], None] = '6435784a8f93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('generated_books',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('subtitle', sa.String(length=500), nullable=True),
    sa.Column('author', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('structure_type', sa.String(length=50), nullable=False),
    sa.Column('content_markdown', sa.Text(), nullable=False),
    sa.Column('content_html', sa.Text(), nullable=True),
    sa.Column('table_of_contents', sa.Text(), nullable=True),
    sa.Column('source_ko_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('chapter_count', sa.Integer(), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_generated_books_created_at'), 'generated_books', ['created_at'], unique=False)
    op.create_index(op.f('ix_generated_books_structure_type'), 'generated_books', ['structure_type'], unique=False)
    op.create_index(op.f('ix_generated_books_title'), 'generated_books', ['title'], unique=False)
    
    op.create_table('book_chapters',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('book_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('source_ko_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['generated_books.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_book_chapters_book_id'), 'book_chapters', ['book_id'], unique=False)
    op.create_index(op.f('ix_book_chapters_order'), 'book_chapters', ['order'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_book_chapters_order'), table_name='book_chapters')
    op.drop_index(op.f('ix_book_chapters_book_id'), table_name='book_chapters')
    op.drop_table('book_chapters')
    op.drop_index(op.f('ix_generated_books_title'), table_name='generated_books')
    op.drop_index(op.f('ix_generated_books_structure_type'), table_name='generated_books')
    op.drop_index(op.f('ix_generated_books_created_at'), table_name='generated_books')
    op.drop_table('generated_books')

"""add interact_events table

Revision ID: a8e411bf9812
Revises: f5dc28be702f
Create Date: 2026-08-15 00:36:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a8e411bf9812'
down_revision: str | Sequence[str] | None = 'f5dc28be702f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'interact_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('block_id', sa.Text(), nullable=False),
        sa.Column('kind', sa.Enum('interact', 'thumbs', 'regenerate', name='interact_kind'), nullable=False),
        sa.Column('action', sa.Text(), nullable=True),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_interact_events_session_created',
        'interact_events',
        ['session_id', 'created_at'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_interact_events_session_created', table_name='interact_events')
    op.drop_table('interact_events')
    op.execute("DROP TYPE IF EXISTS interact_kind;")

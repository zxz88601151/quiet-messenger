"""add refresh_token family_id + revoked_at (H-1 reuse detection)

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.user import UUID  # noqa: E402


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('refresh_tokens', sa.Column('family_id', UUID(), nullable=True))
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'])
    op.add_column(
        'refresh_tokens', sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('refresh_tokens', 'revoked_at')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'family_id')

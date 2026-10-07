"""add login_audit_logs table

Revision ID: a1b2c3d4e5f6
Revises: 92cbfa8e3ee3
Create Date: 2026-08-25 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.user import UUID  # noqa: E402


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '92cbfa8e3ee3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_audit_logs',
        sa.Column('id', UUID(), nullable=False),
        sa.Column('user_id', UUID(), nullable=True),
        sa.Column('identifier', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('failure_reason', sa.String(length=128), nullable=True),
        sa.Column('device_type', sa.String(length=16), nullable=True),
        sa.Column('device_name', sa.String(length=64), nullable=True),
        sa.Column('device_identifier', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_login_audit_logs_action'), 'login_audit_logs', ['action'])
    op.create_index(op.f('ix_login_audit_logs_created_at'), 'login_audit_logs', ['created_at'])
    op.create_index(op.f('ix_login_audit_logs_identifier'), 'login_audit_logs', ['identifier'])
    op.create_index(op.f('ix_login_audit_logs_user_id'), 'login_audit_logs', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_login_audit_logs_user_id'), table_name='login_audit_logs')
    op.drop_index(op.f('ix_login_audit_logs_identifier'), table_name='login_audit_logs')
    op.drop_index(op.f('ix_login_audit_logs_created_at'), table_name='login_audit_logs')
    op.drop_index(op.f('ix_login_audit_logs_action'), table_name='login_audit_logs')
    op.drop_table('login_audit_logs')

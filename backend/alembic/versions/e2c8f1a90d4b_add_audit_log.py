"""add audit_log table

Revision ID: e2c8f1a90d4b
Revises: d9f4a7b2c5e8
Create Date: 2026-05-28 12:30:00.000000

Аудит-лог админских операций (см. backlog «Audit log для админских операций»).
Используется для compliance и расследований.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = 'e2c8f1a90d4b'
down_revision: Union[str, Sequence[str], None] = 'd9f4a7b2c5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('actor_email', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('target_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('target_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('details', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('ip', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['actor_user_id'], ['users.id'], ondelete='SET NULL',
        ),
    )
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_table('audit_log')

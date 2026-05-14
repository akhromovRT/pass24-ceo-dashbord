"""add client_objects and registry fields

Revision ID: 47ecf1978b59
Revises: 2347cbabe6c7
Create Date: 2026-05-14 15:09:42.030344

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '47ecf1978b59'
down_revision: Union[str, Sequence[str], None] = '2347cbabe6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'client_objects',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('cloud_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('object_number', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('object_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('address', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('city_region', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_client_objects_organization_id'),
        'client_objects',
        ['organization_id'],
        unique=False,
    )

    # Add new columns to organizations. in_registry NOT NULL with server_default
    # so existing rows get FALSE without manual UPDATE.
    op.add_column(
        'organizations',
        sa.Column('in_registry', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'organizations',
        sa.Column('contract_1c_raw', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'organizations',
        sa.Column('active_doc_raw', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'organizations',
        sa.Column('objects_count_declared', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_organizations_in_registry'),
        'organizations',
        ['in_registry'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_organizations_in_registry'), table_name='organizations')
    op.drop_column('organizations', 'objects_count_declared')
    op.drop_column('organizations', 'active_doc_raw')
    op.drop_column('organizations', 'contract_1c_raw')
    op.drop_column('organizations', 'in_registry')
    op.drop_index(op.f('ix_client_objects_organization_id'), table_name='client_objects')
    op.drop_table('client_objects')

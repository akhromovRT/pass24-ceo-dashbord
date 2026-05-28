"""add debt_snapshots and debt_snapshot_rows

Revision ID: a3f1b9c47e02
Revises: d8e2b91f5a7c
Create Date: 2026-05-27 09:00:00.000000

Создаёт таблицы debt_snapshots / debt_snapshot_rows для хранения полного
среза 1С на момент каждого импорта файла «Задолженность покупателей».
Этап 2 фикса работы с данными 1С (см. agent_docs/development-history.md).
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "a3f1b9c47e02"
down_revision: Union[str, Sequence[str], None] = "d8e2b91f5a7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEVEL_ENUM = sa.Enum(
    "BUYER",
    "CONTRACT",
    "DOCUMENT",
    name="debtsnapshotlevel",
)


def upgrade() -> None:
    op.create_table(
        "debt_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_run_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("total_debt_start", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_advance_start", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_sold", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_paid", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_prepay_in", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_prepay_used", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_debt_end", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_advance_end", sa.Numeric(14, 2), nullable=True),
        sa.Column("buyers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contracts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyers_no_inn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_run_id"),
    )
    op.create_index(
        op.f("ix_debt_snapshots_import_run_id"),
        "debt_snapshots",
        ["import_run_id"],
        unique=True,
    )

    op.create_table(
        "debt_snapshot_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("parent_row_id", sa.Uuid(), nullable=True),
        sa.Column("level", _LEVEL_ENUM, nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("raw_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("raw_inn", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("contract_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("doc_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("doc_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("doc_date", sa.Date(), nullable=True),
        sa.Column("debt_start", sa.Numeric(14, 2), nullable=True),
        sa.Column("advance_start", sa.Numeric(14, 2), nullable=True),
        sa.Column("sold", sa.Numeric(14, 2), nullable=True),
        sa.Column("paid", sa.Numeric(14, 2), nullable=True),
        sa.Column("prepay_in", sa.Numeric(14, 2), nullable=True),
        sa.Column("prepay_used", sa.Numeric(14, 2), nullable=True),
        sa.Column("debt_end", sa.Numeric(14, 2), nullable=True),
        sa.Column("advance_end", sa.Numeric(14, 2), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["debt_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_row_id"], ["debt_snapshot_rows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_debt_snapshot_rows_snapshot_id"),
        "debt_snapshot_rows",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_debt_snapshot_rows_parent_row_id"),
        "debt_snapshot_rows",
        ["parent_row_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_debt_snapshot_rows_organization_id"),
        "debt_snapshot_rows",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_debt_snapshot_rows_organization_id"), table_name="debt_snapshot_rows")
    op.drop_index(op.f("ix_debt_snapshot_rows_parent_row_id"), table_name="debt_snapshot_rows")
    op.drop_index(op.f("ix_debt_snapshot_rows_snapshot_id"), table_name="debt_snapshot_rows")
    op.drop_table("debt_snapshot_rows")
    op.drop_index(op.f("ix_debt_snapshots_import_run_id"), table_name="debt_snapshots")
    op.drop_table("debt_snapshots")
    sa.Enum(name="debtsnapshotlevel").drop(op.get_bind(), checkfirst=True)

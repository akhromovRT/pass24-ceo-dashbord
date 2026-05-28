"""add debtor_workflow table

Revision ID: b7c4e2f1a890
Revises: a3f1b9c47e02
Create Date: 2026-05-27 14:00:00.000000

Per-organization состояние проработки дебиторки: статус (not_started /
in_progress / done) + текстовый комментарий. Используется в UI «1С-вид»
раздела «Должники» (требование Софьи от 2026-05-26).
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "b7c4e2f1a890"
down_revision: Union[str, Sequence[str], None] = "a3f1b9c47e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STATUS_ENUM = sa.Enum(
    "NOT_STARTED",
    "IN_PROGRESS",
    "DONE",
    name="debtorworkflowstatus",
)


def upgrade() -> None:
    op.create_table(
        "debtor_workflow",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("status", _STATUS_ENUM, nullable=False, server_default="NOT_STARTED"),
        sa.Column("comment", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("organization_id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("debtor_workflow")
    sa.Enum(name="debtorworkflowstatus").drop(op.get_bind(), checkfirst=True)

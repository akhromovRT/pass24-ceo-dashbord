"""add churn_month to organizations

Revision ID: b5d2e9a47c1f
Revises: a2e7c3b1d0f5
Create Date: 2026-05-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b5d2e9a47c1f"
down_revision: Union[str, Sequence[str], None] = "a2e7c3b1d0f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("churn_month", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "churn_month")

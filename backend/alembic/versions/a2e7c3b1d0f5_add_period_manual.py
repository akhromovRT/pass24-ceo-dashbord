"""add period_manual to documents

Revision ID: a2e7c3b1d0f5
Revises: f811cf0c2c38
Create Date: 2026-05-19 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2e7c3b1d0f5"
down_revision: Union[str, Sequence[str], None] = "f811cf0c2c38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "documents",
        sa.Column("period_manual", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "period_manual")

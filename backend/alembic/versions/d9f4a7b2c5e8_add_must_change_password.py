"""add must_change_password to users

Revision ID: d9f4a7b2c5e8
Revises: c8a5b3d1e7f2
Create Date: 2026-05-28 12:00:00.000000

Флаг для force-password-change на первом логине после создания
пользователя через admin UI (см. backlog «Force password change
on first login»).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d9f4a7b2c5e8"
down_revision: Union[str, Sequence[str], None] = "c8a5b3d1e7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")

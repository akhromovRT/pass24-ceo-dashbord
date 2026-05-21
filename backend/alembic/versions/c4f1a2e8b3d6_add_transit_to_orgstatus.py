"""add transit to orgstatus enum

Revision ID: c4f1a2e8b3d6
Revises: b5d2e9a47c1f
Create Date: 2026-05-21 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4f1a2e8b3d6"
down_revision: Union[str, Sequence[str], None] = "b5d2e9a47c1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL ≥9.1: ALTER TYPE ... ADD VALUE безопасен и не блокирует таблицу.
    # COMMIT обязателен перед использованием нового значения.
    op.execute("ALTER TYPE orgstatus ADD VALUE IF NOT EXISTS 'transit'")


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения из enum без пересоздания типа.
    # Если потребуется откат — нужно вручную создать новый enum без 'transit',
    # перевести все TRANSIT-записи в другой статус и заменить тип столбца.
    raise NotImplementedError(
        "Удаление значения из orgstatus требует ручного пересоздания типа."
    )

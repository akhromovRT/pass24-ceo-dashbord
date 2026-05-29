"""add SUPPLIER to OrgStatus enum

Revision ID: f3d7a1c6b9e0
Revises: e2c8f1a90d4b
Create Date: 2026-05-29 14:00:00.000000

P3.0.8a (Софья 2026-05-29): новый статус для контрагентов-поставщиков
(возвраты, не относящиеся к подписочной выручке). Не участвует
в расчёте АП и нигде в статистике CEO-дашборда.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f3d7a1c6b9e0"
down_revision: Union[str, Sequence[str], None] = "e2c8f1a90d4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy для (str, enum.Enum) хранит имя атрибута, не value (см. предыдущие
    # миграции c8a5b3d1e7f2 / c4f1a2e8b3d6). Постгрес ALTER TYPE ADD VALUE требует
    # autocommit, иначе ошибка "cannot run inside a transaction block".
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE orgstatus ADD VALUE IF NOT EXISTS 'SUPPLIER'")


def downgrade() -> None:
    # PostgreSQL не поддерживает DROP VALUE для enum без пересоздания типа.
    pass

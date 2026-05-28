"""add CORRECTION/WRITEOFF/REFUND to DocType enum

Revision ID: c8a5b3d1e7f2
Revises: b7c4e2f1a890
Create Date: 2026-05-28 11:00:00.000000

Парсер debt_report.py распознаёт correction/writeoff/refund как отдельные
типы документов с 2026-05-26, но в БД они маппились в SALE
(_DOC_TYPE_MAP в import_service). Теперь enum doctype содержит их
явно — фильтр «только продажи» в отчётах работает корректно.

PostgreSQL ALTER TYPE ... ADD VALUE — нельзя в транзакции, поэтому
op.execute(...) с autocommit_block.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c8a5b3d1e7f2"
down_revision: Union[str, Sequence[str], None] = "b7c4e2f1a890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL не позволяет ALTER TYPE ... ADD VALUE внутри транзакции
    # (в Alembic >=1.7 это решается через with op.get_context().autocommit_block()).
    # В БД enum doctype хранится с именами в UPPER (SALE/PAYMENT/...),
    # потому что SQLAlchemy для (str, enum.Enum) берёт имя атрибута, не value.
    with op.get_context().autocommit_block():
        for value in ("CORRECTION", "WRITEOFF", "REFUND"):
            op.execute(f"ALTER TYPE doctype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Откат не поддерживается: PostgreSQL не умеет DROP VALUE для enum
    # без пересоздания типа. Если необходимо — пересоздать enum вручную.
    pass

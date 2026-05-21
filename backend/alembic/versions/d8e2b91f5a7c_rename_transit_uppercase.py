"""rename orgstatus 'transit' -> 'TRANSIT' to match other values

SQLAlchemy сериализует enum по .name (UPPERCASE), а не .value (lowercase).
В БД исторические значения хранятся как ACTIVE/CHURNED/SUSPENDED/PROSPECT.
Предыдущая миграция c4f1a2e8b3d6 ошибочно добавила 'transit' lowercase —
PATCH'и со status=transit падали бы с invalid enum value 'TRANSIT'.

Revision ID: d8e2b91f5a7c
Revises: c4f1a2e8b3d6
Create Date: 2026-05-21 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d8e2b91f5a7c"
down_revision: Union[str, Sequence[str], None] = "c4f1a2e8b3d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL ≥10: переименование значения enum безопасно.
    op.execute("ALTER TYPE orgstatus RENAME VALUE 'transit' TO 'TRANSIT'")


def downgrade() -> None:
    op.execute("ALTER TYPE orgstatus RENAME VALUE 'TRANSIT' TO 'transit'")

"""Снимок задолженности из 1С на момент конкретного импорта.

Полностью отражает структуру файла «Задолженность покупателей» из 1С
(Покупатель → Договор → Документ × 8 числовых колонок), включая авансы и
предоплаты, которые в текущей основной модели не сохраняются.

Используется для:
  - представления «1С-вид» в UI раздела «Должники» (этап 3);
  - автосверки между Organization.total_debt и debt_end по 1С (этап 4);
  - истории импортов: можно сравнить два соседних снимка и понять, что
    реально изменилось у конкретного клиента за неделю/месяц.
"""

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class DebtSnapshotLevel(str, enum.Enum):
    BUYER = "buyer"
    CONTRACT = "contract"
    DOCUMENT = "document"


class DebtSnapshot(SQLModel, table=True):
    __tablename__ = "debt_snapshots"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    import_run_id: uuid.UUID = Field(
        foreign_key="import_runs.id",
        unique=True,
        index=True,
    )
    filename: str
    period_start: date | None = None
    period_end: date | None = None

    # Итоги по файлу (суммы всех buyer-строк).
    total_debt_start: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_advance_start: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_sold: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_paid: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_prepay_in: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_prepay_used: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_debt_end: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    total_advance_end: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)

    buyers_count: int = 0
    contracts_count: int = 0
    documents_count: int = 0
    # Покупатели-физлица без ИНН — сохраняем в snapshot, но в Organization не пишем
    # (см. import_service.process_import).
    buyers_no_inn_count: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DebtSnapshotRow(SQLModel, table=True):
    __tablename__ = "debt_snapshot_rows"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    snapshot_id: uuid.UUID = Field(
        foreign_key="debt_snapshots.id",
        index=True,
    )
    parent_row_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="debt_snapshot_rows.id",
        index=True,
    )
    level: DebtSnapshotLevel
    # Порядковый индекс строки в файле — UI отображает в исходном порядке 1С.
    row_index: int

    # Сырые данные из файла.
    raw_name: str
    raw_inn: str | None = None

    # Метаданные.
    contract_number: str | None = None
    contract_date: date | None = None
    doc_type: str | None = None  # sale | payment | correction | writeoff | refund
    doc_number: str | None = None
    doc_date: date | None = None

    # Все 8 числовых колонок файла (NULL = пустая ячейка).
    debt_start: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    advance_start: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    sold: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    paid: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    prepay_in: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    prepay_used: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    debt_end: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    advance_end: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)

    # Связь с актуальными сущностями БД — где удалось сопоставить.
    # Для физлиц без ИНН organization_id = None (полностью допустимый кейс).
    organization_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="organizations.id",
        index=True,
    )
    contract_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="contracts.id",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="documents.id",
    )

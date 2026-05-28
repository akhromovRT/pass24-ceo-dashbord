import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class DocType(str, enum.Enum):
    SALE = "sale"
    PAYMENT = "payment"
    PREPAY_IN = "prepay_in"
    PREPAY_USED = "prepay_used"
    # Корректировки долга / реализации / возвраты / списания — раньше
    # маппились в SALE с raw_name="Корректировка...", что мешало
    # фильтру «только продажи» в отчётах. Добавлены отдельные значения,
    # парсер их выставляет напрямую (см. _DOC_TYPE_MAP).
    CORRECTION = "correction"
    WRITEOFF = "writeoff"
    REFUND = "refund"


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    contract_id: uuid.UUID = Field(foreign_key="contracts.id", index=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    doc_type: DocType
    doc_number: str | None = None
    doc_date: date | None = None
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    period_year: int | None = None
    period_month: int | None = None
    import_run_id: uuid.UUID | None = Field(default=None, foreign_key="import_runs.id")
    raw_name: str | None = None
    period_manual: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class AllocationBasis(str, enum.Enum):
    EXPLICIT_PERIOD = "explicit_period"
    FIFO = "fifo"
    ADVANCE = "advance"
    MANUAL = "manual"


class PaymentAllocation(SQLModel, table=True):
    __tablename__ = "payment_allocations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    payment_document_id: uuid.UUID = Field(foreign_key="documents.id", index=True)
    monthly_charge_id: uuid.UUID | None = Field(
        default=None, foreign_key="monthly_charges.id", index=True
    )
    allocated_amount: Decimal = Field(max_digits=12, decimal_places=2)
    basis: AllocationBasis
    is_manual: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

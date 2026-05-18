import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ChargeSource(str, enum.Enum):
    REALIZATION_1C = "realization_1c"
    SYNTHETIC_TARIFF = "synthetic_tariff"


class MonthlyCharge(SQLModel, table=True):
    __tablename__ = "monthly_charges"
    __table_args__ = (
        UniqueConstraint("organization_id", "year", "month", name="uq_charge_org_period"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    year: int
    month: int
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    source: ChargeSource
    source_document_id: uuid.UUID | None = Field(default=None, foreign_key="documents.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

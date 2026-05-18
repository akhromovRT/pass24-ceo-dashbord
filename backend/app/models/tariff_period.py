import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class TariffPeriod(SQLModel, table=True):
    __tablename__ = "tariff_periods"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    valid_from: date
    monthly_amount: Decimal = Field(max_digits=12, decimal_places=2)
    created_by: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

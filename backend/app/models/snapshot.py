import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint


class MonthlySnapshot(SQLModel, table=True):
    __tablename__ = "monthly_snapshots"
    __table_args__ = (UniqueConstraint("organization_id", "year", "month", "import_run_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    year: int
    month: int = Field(ge=1, le=12)
    debt_start: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    advance_start: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    sold: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    paid: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    sold_ap: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    paid_ap: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    sold_equip: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    paid_equip: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    debt_end: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    advance_end: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    plan_amount: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    collectability: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    dso: int | None = None
    is_active: bool = Field(default=True)
    import_run_id: uuid.UUID | None = Field(default=None, foreign_key="import_runs.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

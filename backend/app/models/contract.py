import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class ContractType(str, enum.Enum):
    SUBSCRIPTION = "subscription"
    EQUIPMENT = "equipment"
    SERVICE = "service"
    OTHER = "other"


class ContractStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class Contract(SQLModel, table=True):
    __tablename__ = "contracts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    contract_number: str | None = None
    contract_date: date | None = None
    contract_type: ContractType = Field(default=ContractType.OTHER)
    classification_source: str | None = None  # auto / manual
    classification_rule: str | None = None
    monthly_amount: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    total_amount: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    status: ContractStatus = Field(default=ContractStatus.ACTIVE)
    raw_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

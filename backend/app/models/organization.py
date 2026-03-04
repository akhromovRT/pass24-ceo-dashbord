import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class OrgType(str, enum.Enum):
    TSN = "TSN"
    OOO = "OOO"
    AO = "AO"
    IP = "IP"
    KP = "KP"
    ZHK = "ZHK"
    SNT = "SNT"
    NP = "NP"
    FL = "FL"
    PROCHEE = "Prochee"


class OrgStatus(str, enum.Enum):
    ACTIVE = "active"
    CHURNED = "churned"
    SUSPENDED = "suspended"
    PROSPECT = "prospect"


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    inn: str = Field(max_length=12, unique=True, index=True)
    name_1c: str
    name_display: str | None = None
    org_type: OrgType | None = None
    manager_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    client_since: date | None = None
    status: OrgStatus = Field(default=OrgStatus.ACTIVE)
    objects: int | None = None
    object_type: str | None = None
    cloud_url: str | None = None
    system_number: str | None = None
    equipment: str | None = None
    address: str | None = None
    city_region: str | None = None
    has_folder: bool | None = None
    payment_score: int | None = Field(default=None, ge=0, le=100)
    monthly_ap: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    total_debt: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

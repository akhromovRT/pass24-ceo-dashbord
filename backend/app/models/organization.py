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
    # Юр.лицо, ранее платившее за другого клиента (или старая карточка
    # после переоформления ИНН). После даты последнего платежа начисления
    # прекращаются, в active_clients и churn-rate не учитывается.
    TRANSIT = "transit"
    # Поставщик: возвраты, попавшие к нам на расчётный счёт. Не участвует
    # в расчёте АП и нигде в статистике (как excluded_from_analytics=True,
    # только именованный статус для удобства). Софья 2026-05-29.
    SUPPLIER = "supplier"


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
    # Месяц последнего начисления АП для клиента в статусе CHURNED.
    # Хранится как первое число месяца. None для всех остальных статусов.
    churn_month: date | None = None
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
    # Поля из реестра «Клиентская база»
    in_registry: bool = Field(default=False, index=True)
    contract_1c_raw: str | None = None
    active_doc_raw: str | None = None
    objects_count_declared: int | None = None
    doc_exchange: str | None = None  # ЭДО / На бумаге / Площадка / None
    excluded_from_analytics: bool = Field(default=False, index=True)
    excluded_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

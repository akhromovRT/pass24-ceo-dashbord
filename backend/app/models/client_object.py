import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ClientObject(SQLModel, table=True):
    """Объект клиента (ЖК / КП / БЦ / база и т.п.). У одной организации
    может быть несколько объектов — каждый со своим cloud_url и адресом."""

    __tablename__ = "client_objects"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organizations.id", index=True)
    name: str = Field(max_length=255)
    cloud_url: str | None = None
    object_number: str | None = None  # "№ объекта в облаке" (может быть несколько через запятую)
    object_type: str | None = None  # ЖК / КП / Логистический центр / Офис и т.д.
    address: str | None = None
    city_region: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

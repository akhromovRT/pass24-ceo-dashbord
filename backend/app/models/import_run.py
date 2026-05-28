import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import JSON
from sqlmodel import Column, Field, SQLModel


class ImportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportRun(SQLModel, table=True):
    __tablename__ = "import_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    filename: str
    file_hash: str = Field(max_length=64)
    period_start: date | None = None
    period_end: date | None = None
    status: ImportStatus = Field(default=ImportStatus.PENDING)
    total_rows: int | None = None
    buyers_count: int | None = None
    contracts_count: int | None = None
    documents_count: int | None = None
    new_buyers: int | None = None
    errors: list | None = Field(default=None, sa_column=Column(JSON))
    delta_summary: dict | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

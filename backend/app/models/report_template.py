import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON
from sqlmodel import Column, Field, SQLModel


class ReportTemplate(SQLModel, table=True):
    """Сохранённый набор критериев отчёта.

    Шаблоны общие для всех пользователей (команда 5 человек); `created_by`
    хранится для пометки автора. `criteria` — произвольный JSON-объект
    (фильтры/колонки/сортировка), его форму задаёт `ReportCriteria`."""

    __tablename__ = "report_templates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    report_type: str = Field(max_length=32)
    criteria: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_by: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

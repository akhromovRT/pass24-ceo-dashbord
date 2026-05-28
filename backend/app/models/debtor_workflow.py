"""Состояние проработки дебиторки по конкретному клиенту.

Привязка к Organization, а не к DebtSnapshotRow — потому что snapshot
пересоздаётся при каждом импорте файла «Задолженность покупателей», а
проработка должника — это история по клиенту, которая должна жить дольше
конкретного среза 1С.

Требование МПП (Софья Морозова, 2026-05-26): в UI «1С-вид» дебиторки
нужны колонки «Проработано / В работе» и текстовый комментарий, которые
менеджер заполняет при разборе списка должников.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class DebtorWorkflowStatus(str, enum.Enum):
    # Базовое состояние: дебиторку ещё не разбирали.
    NOT_STARTED = "not_started"
    # В работе: менеджер связался, ждёт оплату/документы.
    IN_PROGRESS = "in_progress"
    # Проработано: вопрос закрыт по этой строке (платёж принят, списано и т.п.).
    DONE = "done"


class DebtorWorkflow(SQLModel, table=True):
    __tablename__ = "debtor_workflow"

    organization_id: uuid.UUID = Field(
        foreign_key="organizations.id",
        primary_key=True,
    )
    status: DebtorWorkflowStatus = Field(default=DebtorWorkflowStatus.NOT_STARTED)
    comment: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")

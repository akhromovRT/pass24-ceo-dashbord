"""Аудит-лог админских операций.

Что пишем: создание/удаление/смена ролей пользователей, ручные правки
данных через admin-UI (статус клиента, attach/detach платежей и т.п.).

Не пишем: обычные GET'ы, login (для последнего есть отдельный rate-limit
на /auth/login).
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    actor_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    actor_email: str | None = None  # снапшот на случай удаления пользователя
    action: str = Field(
        index=True
    )  # 'user.create', 'user.reset_password', 'org.status_change', ...
    target_type: str | None = None  # 'user', 'organization', 'document', ...
    target_id: str | None = None  # FK как строка (UUID/INN/...)
    details: str | None = None  # JSON-payload для контекста
    ip: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

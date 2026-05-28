import enum
import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    hashed_password: str
    role: UserRole = Field(default=UserRole.VIEWER)
    telegram_id: str | None = None
    is_active: bool = Field(default=True)
    # При создании пользователя через admin UI пароль показывается ОДИН раз;
    # этот флаг заставляет пользователя сменить его при первом логине.
    # Frontend проверяет в /auth/me и редиректит на /profile до смены.
    must_change_password: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

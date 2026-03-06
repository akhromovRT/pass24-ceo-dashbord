import enum
import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class AlertType(str, enum.Enum):
    NON_PAYMENT = "non_payment"
    CHURN_RISK = "churn_risk"
    LARGE_DEBT = "large_debt"
    UNASSIGNED_CLIENT = "unassigned_client"
    PHANTOM_DEAL = "phantom_deal"
    PROJECT_OVERDUE = "project_overdue"
    ANOMALY = "anomaly"
    COLLECTABILITY_DROP = "collectability_drop"
    NEW_CLIENT = "new_client"


class AlertSeverity(str, enum.Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID | None = Field(default=None, foreign_key="organizations.id")
    alert_type: AlertType
    severity: AlertSeverity = Field(default=AlertSeverity.INFO)
    title: str
    description: str | None = None
    metric_value: float | None = None
    threshold: float | None = None
    status: AlertStatus = Field(default=AlertStatus.OPEN)
    resolved_by: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

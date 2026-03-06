import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.database import get_session
from app.models import Alert, AlertStatus

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertStatusUpdate(BaseModel):
    status: AlertStatus


@router.get("")
def list_alerts(
    status: AlertStatus | None = None,
    session: Session = Depends(get_session),
):
    query = select(Alert).order_by(Alert.created_at.desc())  # type: ignore[union-attr]
    if status:
        query = query.where(Alert.status == status)
    return session.exec(query).all()


@router.patch("/{alert_id}")
def update_alert_status(
    alert_id: uuid.UUID,
    body: AlertStatusUpdate,
    session: Session = Depends(get_session),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = body.status
    if body.status in (AlertStatus.RESOLVED, AlertStatus.DISMISSED):
        alert.resolved_at = datetime.now(UTC)
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert

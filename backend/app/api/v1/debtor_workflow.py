"""API для проработки дебиторки (статус + комментарий по клиенту).

Используется в UI «1С-вид» раздела «Должники»: менеджер прямо в строке
buyer-уровня меняет статус («Не начато / В работе / Проработано») и
добавляет текстовый комментарий. Привязка к Organization, поэтому
состояние переживает любой новый импорт 1С.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import (
    DebtorWorkflow, DebtorWorkflowStatus, Organization, User,
)

router = APIRouter(
    prefix="/debtor-workflow",
    tags=["debtor-workflow"],
    dependencies=[Depends(get_current_user)],
)


class WorkflowUpdate(BaseModel):
    # Хотя бы одно поле должно быть указано — проверяем в обработчике.
    status: DebtorWorkflowStatus | None = None
    comment: str | None = None


def _serialize(
    wf: DebtorWorkflow, user_name: str | None = None,
) -> dict:
    return {
        "organization_id": str(wf.organization_id),
        "status": wf.status.value if hasattr(wf.status, "value") else wf.status,
        "comment": wf.comment,
        "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
        "updated_by_id": str(wf.updated_by_id) if wf.updated_by_id else None,
        "updated_by_name": user_name,
    }


@router.put("/{organization_id}")
def upsert_workflow(
    organization_id: uuid.UUID,
    payload: WorkflowUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if payload.status is None and payload.comment is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: status, comment",
        )

    org = session.get(Organization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    wf = session.get(DebtorWorkflow, organization_id)
    if wf is None:
        wf = DebtorWorkflow(
            organization_id=organization_id,
            status=payload.status or DebtorWorkflowStatus.NOT_STARTED,
            comment=payload.comment,
            updated_by_id=user.id,
        )
        session.add(wf)
    else:
        if payload.status is not None:
            wf.status = payload.status
        if payload.comment is not None:
            wf.comment = payload.comment
        wf.updated_at = datetime.now(UTC)
        wf.updated_by_id = user.id

    session.commit()
    session.refresh(wf)
    return _serialize(wf, user_name=user.name or user.email)


def load_workflow_map(
    session: Session, organization_ids: set[uuid.UUID]
) -> dict[str, dict]:
    """Возвращает {org_id_str: serialized_workflow} для переданных организаций.

    Используется в /debt-snapshots, чтобы отдать workflow на каждый buyer
    одним SQL-запросом.
    """
    if not organization_ids:
        return {}
    wfs = session.exec(
        select(DebtorWorkflow).where(
            DebtorWorkflow.organization_id.in_(organization_ids)  # type: ignore[union-attr]
        )
    ).all()
    user_ids = {w.updated_by_id for w in wfs if w.updated_by_id}
    users_map: dict[uuid.UUID, str] = {}
    if user_ids:
        users = session.exec(
            select(User).where(User.id.in_(user_ids))  # type: ignore[union-attr]
        ).all()
        users_map = {u.id: (u.name or u.email) for u in users}
    return {
        str(w.organization_id): _serialize(w, user_name=users_map.get(w.updated_by_id))
        for w in wfs
    }

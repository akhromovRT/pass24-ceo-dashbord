"""API модуля «Отчёты»: preview, экспорт в Excel, CRUD сохранённых шаблонов."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import ReportTemplate, User
from app.services.report_service import (
    REPORTS,
    ReportCriteria,
    build_report,
    columns_for,
    report_to_xlsx,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _check_type(report_type: str) -> None:
    if report_type not in REPORTS:
        raise HTTPException(status_code=404, detail="unknown report type")


# --- шаблоны критериев ------------------------------------------------------


class TemplateCreate(BaseModel):
    name: str
    report_type: str
    criteria: dict = {}


@router.get("/templates")
def list_templates(session: Session = Depends(get_session)):
    return session.exec(
        select(ReportTemplate).order_by(col(ReportTemplate.created_at).desc())
    ).all()


@router.post("/templates", status_code=201)
def create_template(
    payload: TemplateCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _check_type(payload.report_type)
    template = ReportTemplate(
        name=payload.name,
        report_type=payload.report_type,
        criteria=payload.criteria,
        created_by=user.id,
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: uuid.UUID,
    session: Session = Depends(get_session),
):
    template = session.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    session.delete(template)
    session.commit()
    return {"status": "ok"}


# --- генерация отчёта -------------------------------------------------------


@router.post("/{report_type}/preview")
def report_preview(
    report_type: str,
    criteria: ReportCriteria,
    session: Session = Depends(get_session),
):
    _check_type(report_type)
    rows = build_report(report_type, session, criteria)
    columns = columns_for(report_type, criteria)
    return {
        "columns": [{"key": key, "header": header} for key, header in columns],
        "rows": rows,
        "total": len(rows),
    }


@router.post("/{report_type}/export")
def report_export(
    report_type: str,
    criteria: ReportCriteria,
    session: Session = Depends(get_session),
):
    _check_type(report_type)
    rows = build_report(report_type, session, criteria)
    columns = columns_for(report_type, criteria)
    content = report_to_xlsx(report_type, columns, rows)
    filename = f"{report_type}-{date.today().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

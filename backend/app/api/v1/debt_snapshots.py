"""API для UI «1С-вид» в разделе «Должники» (этап 3).

Эндпоинты:
- GET /debt-snapshots          — список доступных снимков (мета-данные)
- GET /debt-snapshots/latest   — последний снимок + строки + сверка с БД
- GET /debt-snapshots/{id}     — конкретный снимок + строки + сверка с БД
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import (
    DebtSnapshot, DebtSnapshotLevel, DebtSnapshotRow, Organization,
)

router = APIRouter(
    prefix="/debt-snapshots",
    tags=["debt-snapshots"],
    dependencies=[Depends(get_current_user)],
)


def _serialize_snapshot_meta(snap: DebtSnapshot) -> dict:
    return {
        "id": str(snap.id),
        "import_run_id": str(snap.import_run_id),
        "filename": snap.filename,
        "period_start": snap.period_start.isoformat() if snap.period_start else None,
        "period_end": snap.period_end.isoformat() if snap.period_end else None,
        "total_debt_start": _f(snap.total_debt_start),
        "total_advance_start": _f(snap.total_advance_start),
        "total_sold": _f(snap.total_sold),
        "total_paid": _f(snap.total_paid),
        "total_prepay_in": _f(snap.total_prepay_in),
        "total_prepay_used": _f(snap.total_prepay_used),
        "total_debt_end": _f(snap.total_debt_end),
        "total_advance_end": _f(snap.total_advance_end),
        "buyers_count": snap.buyers_count,
        "contracts_count": snap.contracts_count,
        "documents_count": snap.documents_count,
        "buyers_no_inn_count": snap.buyers_no_inn_count,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }


def _f(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _serialize_row(row: DebtSnapshotRow) -> dict:
    return {
        "id": str(row.id),
        "parent_row_id": str(row.parent_row_id) if row.parent_row_id else None,
        "level": row.level.value if hasattr(row.level, "value") else row.level,
        "row_index": row.row_index,
        "raw_name": row.raw_name,
        "raw_inn": row.raw_inn,
        "contract_number": row.contract_number,
        "contract_date": row.contract_date.isoformat() if row.contract_date else None,
        "doc_type": row.doc_type,
        "doc_number": row.doc_number,
        "doc_date": row.doc_date.isoformat() if row.doc_date else None,
        "debt_start": _f(row.debt_start),
        "advance_start": _f(row.advance_start),
        "sold": _f(row.sold),
        "paid": _f(row.paid),
        "prepay_in": _f(row.prepay_in),
        "prepay_used": _f(row.prepay_used),
        "debt_end": _f(row.debt_end),
        "advance_end": _f(row.advance_end),
        "organization_id": str(row.organization_id) if row.organization_id else None,
        "contract_id": str(row.contract_id) if row.contract_id else None,
        "document_id": str(row.document_id) if row.document_id else None,
    }


def _build_full_response(session: Session, snap: DebtSnapshot) -> dict:
    rows = session.exec(
        select(DebtSnapshotRow)
        .where(DebtSnapshotRow.snapshot_id == snap.id)
        .order_by(DebtSnapshotRow.row_index)
    ).all()

    # Сверка с актуальной БД по уровню BUYER:
    # для каждой buyer-строки с organization_id берём Organization.total_debt
    # и сравниваем с DebtSnapshotRow.debt_end. Помечаем расхождения > 1 ₽.
    org_ids = {r.organization_id for r in rows if r.organization_id}
    actual_totals: dict[str, dict] = {}
    if org_ids:
        orgs = session.exec(
            select(Organization).where(Organization.id.in_(org_ids))  # type: ignore[union-attr]
        ).all()
        for o in orgs:
            actual_totals[str(o.id)] = {
                "name_display": o.name_display,
                "name_1c": o.name_1c,
                "actual_total_debt": _f(o.total_debt),
                "status": o.status.value if hasattr(o.status, "value") else o.status,
                "excluded_from_analytics": o.excluded_from_analytics,
            }

    diffs = []
    for r in rows:
        if r.level != DebtSnapshotLevel.BUYER or not r.organization_id:
            continue
        info = actual_totals.get(str(r.organization_id))
        if not info:
            continue
        file_debt = float(r.debt_end or 0)
        db_debt = info["actual_total_debt"] or 0
        delta = file_debt - db_debt
        if abs(delta) > 1.0 and not info["excluded_from_analytics"]:
            diffs.append({
                "row_id": str(r.id),
                "organization_id": str(r.organization_id),
                "inn": r.raw_inn,
                "name": info["name_display"] or info["name_1c"] or r.raw_name,
                "file_debt_end": file_debt,
                "db_total_debt": db_debt,
                "delta": delta,
                "status": info["status"],
            })

    return {
        "snapshot": _serialize_snapshot_meta(snap),
        "rows": [_serialize_row(r) for r in rows],
        "actual_org_totals": actual_totals,
        "diffs": diffs,
    }


@router.get("")
def list_snapshots(session: Session = Depends(get_session)):
    """Список всех снимков (новейшие сверху). Для дропдауна выбора импорта."""
    snaps = session.exec(
        select(DebtSnapshot).order_by(DebtSnapshot.created_at.desc())  # type: ignore[union-attr]
    ).all()
    return [_serialize_snapshot_meta(s) for s in snaps]


@router.get("/latest")
def get_latest_snapshot(session: Session = Depends(get_session)):
    snap = session.exec(
        select(DebtSnapshot).order_by(DebtSnapshot.created_at.desc())  # type: ignore[union-attr]
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="No debt snapshots yet")
    return _build_full_response(session, snap)


@router.get("/{snapshot_id}")
def get_snapshot(snapshot_id: uuid.UUID, session: Session = Depends(get_session)):
    snap = session.exec(
        select(DebtSnapshot).where(DebtSnapshot.id == snapshot_id)
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return _build_full_response(session, snap)

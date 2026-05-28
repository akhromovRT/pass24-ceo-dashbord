"""API для UI «1С-вид» в разделе «Должники» (этап 3).

Эндпоинты:
- GET /debt-snapshots          — список доступных снимков (мета-данные)
- GET /debt-snapshots/latest   — последний снимок + строки + сверка с БД
- GET /debt-snapshots/{id}     — конкретный снимок + строки + сверка с БД
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.api.v1.debtor_workflow import load_workflow_map
from app.core.database import get_session
from app.models import (
    DebtSnapshot,
    DebtSnapshotLevel,
    DebtSnapshotRow,
    Organization,
    OrgStatus,
)

# Какие статусы клиентов считаются «нашими постоянными» при фильтре
# only_regular (МПП Софья, 2026-05-26): активные + временно приостановленные
# + ушедшие в отток (по ним долг может оставаться, надо прорабатывать).
# Транзитные и потенциальные — отсекаем, это шум для дебиторки.
_REGULAR_STATUSES = {OrgStatus.ACTIVE, OrgStatus.SUSPENDED, OrgStatus.CHURNED}

# По комментарию Софьи от 2026-05-28 — нужен и более узкий срез
# «только активные клиенты», поэтому фильтр параметризуется через
# query-параметр org_statuses (csv). only_regular остаётся как обратно
# совместимый алиас на _REGULAR_STATUSES.
_VALID_STATUS_TOKENS = {s.value for s in OrgStatus}


def _parse_org_statuses(raw: str | None) -> set[OrgStatus] | None:
    """csv 'active,suspended' → set[OrgStatus]. Невалидные токены игнорируем."""
    if not raw:
        return None
    tokens = {t.strip().lower() for t in raw.split(",") if t.strip()}
    if not tokens:
        return None
    parsed = {OrgStatus(t) for t in tokens if t in _VALID_STATUS_TOKENS}
    return parsed or None


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


def _build_full_response(
    session: Session,
    snap: DebtSnapshot,
    only_regular: bool = False,
    org_statuses: set[OrgStatus] | None = None,
) -> dict:
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
    org_full_map: dict[uuid.UUID, Organization] = {}
    if org_ids:
        orgs = session.exec(
            select(Organization).where(Organization.id.in_(org_ids))  # type: ignore[union-attr]
        ).all()
        for o in orgs:
            org_full_map[o.id] = o
            actual_totals[str(o.id)] = {
                "name_display": o.name_display,
                "name_1c": o.name_1c,
                "actual_total_debt": _f(o.total_debt),
                "status": o.status.value if hasattr(o.status, "value") else o.status,
                "excluded_from_analytics": o.excluded_from_analytics,
                "in_registry": o.in_registry,
            }

    # Workflow проработки по каждому buyer (status + comment) — одним SELECT.
    workflow_map = load_workflow_map(session, org_ids)

    # Фильтр по статусам клиента (P3.0.2): если задан org_statuses — используем
    # его (узкий срез, например только active). Иначе если only_regular=true —
    # используем _REGULAR_STATUSES (обратно совместимый алиас). В обоих случаях
    # требуем in_registry=True. Затем каскадно включаем детей по parent_row_id.
    effective_statuses: set[OrgStatus] | None = None
    if org_statuses:
        effective_statuses = org_statuses
    elif only_regular:
        effective_statuses = _REGULAR_STATUSES

    if effective_statuses is not None:
        allowed_buyer_ids: set[uuid.UUID] = set()
        for r in rows:
            if r.level != DebtSnapshotLevel.BUYER:
                continue
            org = org_full_map.get(r.organization_id) if r.organization_id else None
            if org and org.in_registry and org.status in effective_statuses:
                allowed_buyer_ids.add(r.id)

        # Каскад: child включается, если parent в разрешённом множестве
        # (для дерева buyer→contract→document достаточно одного прохода
        # по row_index, потому что parent всегда идёт раньше child в файле).
        allowed_row_ids = set(allowed_buyer_ids)
        for r in rows:
            if r.id in allowed_row_ids:
                continue
            if r.parent_row_id and r.parent_row_id in allowed_row_ids:
                allowed_row_ids.add(r.id)
        rows = [r for r in rows if r.id in allowed_row_ids]

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
            diffs.append(
                {
                    "row_id": str(r.id),
                    "organization_id": str(r.organization_id),
                    "inn": r.raw_inn,
                    "name": info["name_display"] or info["name_1c"] or r.raw_name,
                    "file_debt_end": file_debt,
                    "db_total_debt": db_debt,
                    "delta": delta,
                    "status": info["status"],
                }
            )

    return {
        "snapshot": _serialize_snapshot_meta(snap),
        "rows": [_serialize_row(r) for r in rows],
        "actual_org_totals": actual_totals,
        "workflow_by_org": workflow_map,
        "diffs": diffs,
        "only_regular": only_regular,
        "org_statuses": (
            sorted(s.value for s in effective_statuses) if effective_statuses is not None else None
        ),
    }


@router.get("")
def list_snapshots(session: Session = Depends(get_session)):
    """Список всех снимков (новейшие сверху). Для дропдауна выбора импорта."""
    snaps = session.exec(
        select(DebtSnapshot).order_by(DebtSnapshot.created_at.desc())  # type: ignore[union-attr]
    ).all()
    return [_serialize_snapshot_meta(s) for s in snaps]


@router.get("/latest")
def get_latest_snapshot(
    only_regular: bool = Query(default=False),
    org_statuses: str | None = Query(
        default=None,
        description="CSV статусов (active,suspended,churned,transit,prospect). "
        "Если задан — приоритетнее only_regular.",
    ),
    session: Session = Depends(get_session),
):
    snap = session.exec(
        select(DebtSnapshot).order_by(DebtSnapshot.created_at.desc())  # type: ignore[union-attr]
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="No debt snapshots yet")
    return _build_full_response(
        session,
        snap,
        only_regular=only_regular,
        org_statuses=_parse_org_statuses(org_statuses),
    )


@router.get("/{snapshot_id}")
def get_snapshot(
    snapshot_id: uuid.UUID,
    only_regular: bool = Query(default=False),
    org_statuses: str | None = Query(
        default=None,
        description="CSV статусов (active,suspended,churned,transit,prospect). "
        "Если задан — приоритетнее only_regular.",
    ),
    session: Session = Depends(get_session),
):
    snap = session.exec(select(DebtSnapshot).where(DebtSnapshot.id == snapshot_id)).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return _build_full_response(
        session,
        snap,
        only_regular=only_regular,
        org_statuses=_parse_org_statuses(org_statuses),
    )

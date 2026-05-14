"""CEO24 Dashboard API.

Все аналитические эндпоинты автоматически фильтруют организации с
excluded_from_analytics=True."""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import (
    Alert, AlertStatus, Contract, ContractStatus, ContractType,
    Document, DocType, MonthlySnapshot, Organization, OrgStatus,
)

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


def _excl():
    return Organization.excluded_from_analytics == False  # noqa: E712


def _months_back(n: int) -> list[tuple[int, int]]:
    today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12; y -= 1
    return list(reversed(out))


def _f(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def _plan_mrr_total(session: Session) -> float:
    """Источник истины для plan MRR: Organization.monthly_ap (из аналитики /
    реестра). Используем потому что Contract.monthly_amount заполнен только
    у меньшинства контрактов."""
    v = session.exec(
        select(func.coalesce(func.sum(Organization.monthly_ap), 0))
        .where(_excl(), Organization.status == OrgStatus.ACTIVE)
    ).one()
    return _f(v)


def _fact_mrr_for_month(session: Session, year: int, month: int) -> float:
    """Сумма всех PAYMENT за месяц. Без фильтра по типу контракта — bank-import
    создаёт OTHER-контракты, но платежи там реальные. Исключения через JOIN
    с Organization."""
    v = session.exec(
        select(func.coalesce(func.sum(Document.amount), 0))
        .join(Organization, Organization.id == Document.organization_id)
        .where(
            _excl(),
            Document.doc_type == DocType.PAYMENT,
            func.extract("year", Document.doc_date) == year,
            func.extract("month", Document.doc_date) == month,
        )
    ).one()
    return _f(v)


@router.get("/summary")
def dashboard_summary(session: Session = Depends(get_session)):
    plan_mrr = _plan_mrr_total(session)

    today = date.today()
    prev_y, prev_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    prev2_y, prev2_m = (prev_y, prev_m - 1) if prev_m > 1 else (prev_y - 1, 12)

    fact_mrr = _fact_mrr_for_month(session, prev_y, prev_m)
    fact_mrr_prev = _fact_mrr_for_month(session, prev2_y, prev2_m)

    mom_pct = None
    if fact_mrr_prev > 0:
        mom_pct = round((fact_mrr - fact_mrr_prev) / fact_mrr_prev * 100, 1)

    total_debt = _f(session.exec(
        select(func.coalesce(func.sum(Organization.total_debt), 0)).where(_excl())
    ).one())

    active_clients = session.exec(
        select(func.count()).select_from(Organization)
        .where(_excl(), Organization.status == OrgStatus.ACTIVE)
    ).one()

    open_alerts = session.exec(
        select(func.count()).select_from(Alert)
        .join(Organization, Organization.id == Alert.organization_id)
        .where(_excl(), Alert.status == AlertStatus.OPEN)
    ).one()

    cutoff_30 = today - timedelta(days=30)
    cutoff_60 = today - timedelta(days=60)
    cutoff_90 = today - timedelta(days=90)

    # Новые — у кого МИН doc_date PAYMENT попал в окно
    new_30d = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id).distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(
                _excl(),
                Document.doc_type == DocType.PAYMENT,
            )
            .group_by(Document.organization_id)
            .having(func.min(Document.doc_date) >= cutoff_30)
            .subquery()
        )
    ).one()
    new_90d = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id).distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(
                _excl(),
                Document.doc_type == DocType.PAYMENT,
            )
            .group_by(Document.organization_id)
            .having(func.min(Document.doc_date) >= cutoff_90)
            .subquery()
        )
    ).one()

    # Ушедшие: активные клиенты с положительным monthly_ap у которых нет PAYMENT за 60 дней
    paying_active = session.exec(
        select(Organization.id)
        .where(
            _excl(),
            Organization.status == OrgStatus.ACTIVE,
            Organization.monthly_ap.is_not(None),  # type: ignore[union-attr]
            Organization.monthly_ap > 0,  # type: ignore[operator]
        )
    ).all()
    recently_paid_ids = set(session.exec(
        select(Document.organization_id).distinct()
        .where(Document.doc_type == DocType.PAYMENT, Document.doc_date >= cutoff_60)
    ).all())
    churned_60d = sum(1 for oid in paying_active if oid not in recently_paid_ids)

    return {
        "mrr_fact": fact_mrr,
        "mrr_plan": plan_mrr,
        "arr_plan": plan_mrr * 12,
        "total_debt": total_debt,
        "active_clients": active_clients,
        "open_alerts": open_alerts,
        "new_30d": new_30d,
        "new_90d": new_90d,
        "churned_60d": churned_60d,
        "mom_mrr_delta_pct": mom_pct,
        "fact_month": f"{prev_y}-{prev_m:02d}",
        "mrr": fact_mrr,
        "arr": plan_mrr * 12,
    }


@router.get("/mrr-plan-vs-fact")
def mrr_plan_vs_fact(months: int = 12, session: Session = Depends(get_session)):
    plan_mrr = _plan_mrr_total(session)
    series = []
    for y, m in _months_back(months):
        fact = _fact_mrr_for_month(session, y, m)
        series.append({
            "year": y, "month": m, "label": f"{m:02d}/{y}",
            "plan": plan_mrr, "fact": fact,
            "ratio": round(fact / plan_mrr * 100, 1) if plan_mrr else None,
        })
    return series


@router.get("/aging")
def aging_buckets(session: Session = Depends(get_session)):
    orgs = session.exec(
        select(Organization).where(
            _excl(),
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()

    buckets = {"0-30": [], "31-60": [], "61-90": [], "90+": []}
    for org in orgs:
        debt = _f(org.total_debt)
        monthly = _f(org.monthly_ap) or 1
        months_overdue = debt / monthly if monthly > 0 else 999
        if months_overdue <= 1: key = "0-30"
        elif months_overdue <= 2: key = "31-60"
        elif months_overdue <= 3: key = "61-90"
        else: key = "90+"
        buckets[key].append(org)
    return [
        {"bucket": k, "amount": round(sum(_f(o.total_debt) for o in v), 2), "count": len(v)}
        for k, v in buckets.items()
    ]


@router.get("/aging/{bucket}")
def aging_bucket_detail(bucket: str, session: Session = Depends(get_session)):
    if bucket not in ("0-30", "31-60", "61-90", "90+"):
        raise HTTPException(status_code=400, detail="invalid bucket")
    orgs = session.exec(
        select(Organization).where(
            _excl(),
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()
    rows = []
    for org in orgs:
        debt = _f(org.total_debt)
        monthly = _f(org.monthly_ap) or 1
        months_overdue = debt / monthly if monthly > 0 else 999
        if bucket == "0-30" and months_overdue > 1: continue
        if bucket == "31-60" and not (1 < months_overdue <= 2): continue
        if bucket == "61-90" and not (2 < months_overdue <= 3): continue
        if bucket == "90+" and months_overdue <= 3: continue
        rows.append({
            "inn": org.inn,
            "name": org.name_display or org.name_1c,
            "monthly_ap": _f(org.monthly_ap),
            "total_debt": debt,
            "months_overdue": round(months_overdue, 1),
            "status": org.status,
        })
    rows.sort(key=lambda r: -r["total_debt"])
    return rows


@router.get("/mrr-trend")
def mrr_trend(session: Session = Depends(get_session)):
    results = session.exec(
        select(
            MonthlySnapshot.year, MonthlySnapshot.month,
            func.sum(MonthlySnapshot.sold_ap).label("sold_ap"),
            func.sum(MonthlySnapshot.paid_ap).label("paid_ap"),
        )
        .join(Organization, Organization.id == MonthlySnapshot.organization_id)
        .where(_excl())
        .group_by(MonthlySnapshot.year, MonthlySnapshot.month)
        .order_by(MonthlySnapshot.year, MonthlySnapshot.month)
    ).all()
    return [{"year": r[0], "month": r[1], "sold_ap": _f(r[2]), "paid_ap": _f(r[3])} for r in results]


@router.get("/payment-matrix")
def payment_matrix(months: int = 12, session: Session = Depends(get_session)):
    """Шахматка: один ряд на каждого активного клиента с monthly_ap > 0.
    Колонки — месяцы. План = Organization.monthly_ap (константа по столбцам).
    Факт = сумма ВСЕХ PAYMENT за месяц (включая bank-import контракты)."""
    month_keys = _months_back(months)
    month_labels = [f"{m:02d}/{y}" for y, m in month_keys]
    y_min, m_min = month_keys[0]
    cutoff = date(y_min, m_min, 1)

    orgs = session.exec(
        select(Organization)
        .where(
            _excl(),
            Organization.status == OrgStatus.ACTIVE,
            Organization.monthly_ap.is_not(None),  # type: ignore[union-attr]
            Organization.monthly_ap > 0,  # type: ignore[operator]
        )
        .order_by(Organization.monthly_ap.desc())  # type: ignore[union-attr]
    ).all()

    org_ids = [o.id for o in orgs]
    if not org_ids:
        return {"months": month_labels, "orgs": [], "cells": []}

    pay_rows = session.exec(
        select(
            Document.organization_id,
            func.extract("year", Document.doc_date).label("y"),
            func.extract("month", Document.doc_date).label("m"),
            func.sum(Document.amount).label("paid"),
        )
        .where(
            Document.doc_type == DocType.PAYMENT,
            Document.organization_id.in_(org_ids),  # type: ignore[union-attr]
            Document.doc_date >= cutoff,
        )
        .group_by(Document.organization_id, "y", "m")
    ).all()
    paid_lookup = {(oid, int(y), int(m)): _f(p) for oid, y, m, p in pay_rows}

    orgs_out, cells = [], []
    for oi, org in enumerate(orgs):
        plan = _f(org.monthly_ap)
        total_paid = 0.0
        for mi, (y, m) in enumerate(month_keys):
            paid = paid_lookup.get((org.id, y, m), 0.0)
            total_paid += paid
            ratio = round(paid / plan * 100, 0) if plan > 0 else None
            cells.append({
                "row": oi, "col": mi,
                "paid": round(paid, 2), "plan": round(plan, 2), "ratio": ratio,
            })
        orgs_out.append({
            "id": str(org.id),
            "inn": org.inn,
            "name": org.name_display or org.name_1c,
            "monthly_plan": round(plan, 2),
            "total_paid_period": round(total_paid, 2),
            "expected_period": round(plan * len(month_keys), 2),
        })

    return {"months": month_labels, "orgs": orgs_out, "cells": cells}

"""CEO24 Dashboard API.

Все аналитические эндпоинты автоматически фильтруют организации с
excluded_from_analytics=True (например, РРСС НЕДВИЖИМОСТЬ ООО — токсичный
выброс долга, искажающий метрики)."""
from datetime import date, datetime, timedelta
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
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


def _excl():
    """Фильтр-предикат: только организации НЕ-исключённые из аналитики."""
    return Organization.excluded_from_analytics == False  # noqa: E712


def _today_year_month():
    today = date.today()
    return today.year, today.month


def _months_back(n: int) -> list[tuple[int, int]]:
    """Список (year, month) для последних n месяцев включительно, по возрастанию."""
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def _f(x):
    if x is None:
        return 0.0
    if isinstance(x, Decimal):
        return float(x)
    return float(x)


# ----- /summary --------------------------------------------------

@router.get("/summary")
def dashboard_summary(session: Session = Depends(get_session)):
    """Сводка для верхнего блока KPI.

    Возвращает:
      mrr_fact / mrr_plan / arr / total_debt / active_clients / open_alerts
      new_30d / new_90d        — новых организаций за 30/90 дней
      churned_60d              — клиенты, у которых нет ни одного PAYMENT за 60 дней (среди подписочных)
      mom_mrr_delta_pct        — изменение MRR относительно прошлого месяца
    """
    # Plan MRR — сумма monthly_amount по активным контрактам типа subscription
    plan_mrr = session.exec(
        select(func.coalesce(func.sum(Contract.monthly_amount), 0))
        .join(Organization, Organization.id == Contract.organization_id)
        .where(
            _excl(),
            Contract.status == ContractStatus.ACTIVE,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            Contract.monthly_amount.is_not(None),  # type: ignore[union-attr]
        )
    ).one()

    # Fact MRR — выручка за последний полный месяц (Document doc_type=PAYMENT и тип контракта subscription)
    y, m = _today_year_month()
    # Предыдущий месяц
    prev_y, prev_m = (y, m - 1) if m > 1 else (y - 1, 12)
    fact_mrr = session.exec(
        select(func.coalesce(func.sum(Document.amount), 0))
        .join(Contract, Contract.id == Document.contract_id)
        .join(Organization, Organization.id == Document.organization_id)
        .where(
            _excl(),
            Document.doc_type == DocType.PAYMENT,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            func.extract("year", Document.doc_date) == prev_y,
            func.extract("month", Document.doc_date) == prev_m,
        )
    ).one()

    # MRR два месяца назад — для MoM-дельты
    prev2_y, prev2_m = (prev_y, prev_m - 1) if prev_m > 1 else (prev_y - 1, 12)
    mrr_two_back = session.exec(
        select(func.coalesce(func.sum(Document.amount), 0))
        .join(Contract, Contract.id == Document.contract_id)
        .join(Organization, Organization.id == Document.organization_id)
        .where(
            _excl(),
            Document.doc_type == DocType.PAYMENT,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            func.extract("year", Document.doc_date) == prev2_y,
            func.extract("month", Document.doc_date) == prev2_m,
        )
    ).one()

    mom_pct = None
    if _f(mrr_two_back) > 0:
        mom_pct = round((_f(fact_mrr) - _f(mrr_two_back)) / _f(mrr_two_back) * 100, 1)

    total_debt = session.exec(
        select(func.coalesce(func.sum(Organization.total_debt), 0))
        .where(_excl())
    ).one()

    active_clients = session.exec(
        select(func.count()).select_from(Organization).where(
            _excl(), Organization.status == OrgStatus.ACTIVE
        )
    ).one()

    open_alerts = session.exec(
        select(func.count()).select_from(Alert)
        .join(Organization, Organization.id == Alert.organization_id)
        .where(_excl(), Alert.status == AlertStatus.OPEN)
    ).one()

    today = date.today()
    cutoff_30 = today - timedelta(days=30)
    cutoff_90 = today - timedelta(days=90)
    cutoff_60 = today - timedelta(days=60)

    # «Новые» — у кого первый PAYMENT за последние N дней
    new_30d = session.exec(
        select(func.count(func.distinct(Organization.id)))
        .select_from(Organization)
        .join(Document, Document.organization_id == Organization.id)
        .where(
            _excl(), Document.doc_type == DocType.PAYMENT,
            Organization.id.in_(  # type: ignore[union-attr]
                select(Document.organization_id).group_by(Document.organization_id)
                .having(func.min(Document.doc_date) >= cutoff_30)
            ),
        )
    ).one()
    new_90d = session.exec(
        select(func.count(func.distinct(Organization.id)))
        .select_from(Organization)
        .join(Document, Document.organization_id == Organization.id)
        .where(
            _excl(), Document.doc_type == DocType.PAYMENT,
            Organization.id.in_(  # type: ignore[union-attr]
                select(Document.organization_id).group_by(Document.organization_id)
                .having(func.min(Document.doc_date) >= cutoff_90)
            ),
        )
    ).one()

    # «Ушедшие» — активные подписочные клиенты у которых НЕТ платежей за последние 60 дней
    subscribers_ids = session.exec(
        select(Organization.id).distinct()
        .join(Contract, Contract.organization_id == Organization.id)
        .where(
            _excl(),
            Organization.status == OrgStatus.ACTIVE,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            Contract.status == ContractStatus.ACTIVE,
        )
    ).all()
    recently_paid_ids = set(session.exec(
        select(Document.organization_id).distinct()
        .where(
            Document.doc_type == DocType.PAYMENT,
            Document.doc_date >= cutoff_60,
        )
    ).all())
    churned_60d = sum(1 for sid in subscribers_ids if sid not in recently_paid_ids)

    return {
        "mrr_fact": _f(fact_mrr),
        "mrr_plan": _f(plan_mrr),
        "arr_plan": _f(plan_mrr) * 12,
        "total_debt": _f(total_debt),
        "active_clients": active_clients,
        "open_alerts": open_alerts,
        "new_30d": new_30d,
        "new_90d": new_90d,
        "churned_60d": churned_60d,
        "mom_mrr_delta_pct": mom_pct,
        "fact_month": f"{prev_y}-{prev_m:02d}",
        # Compat with old UI:
        "mrr": _f(fact_mrr),
        "arr": _f(plan_mrr) * 12,
    }


# ----- /mrr-plan-vs-fact -----------------------------------------

@router.get("/mrr-plan-vs-fact")
def mrr_plan_vs_fact(months: int = 12, session: Session = Depends(get_session)):
    """Помесячно: план (сумма active subscription monthly_amount, константа)
    vs факт (PAYMENT по subscription-контрактам за месяц).

    План считается константой — текущий plan_mrr применяется ко всем месяцам,
    что даёт «целевую линию» как ориентир. (Исторических планов мы не храним.)
    """
    plan_mrr = session.exec(
        select(func.coalesce(func.sum(Contract.monthly_amount), 0))
        .join(Organization, Organization.id == Contract.organization_id)
        .where(
            _excl(),
            Contract.status == ContractStatus.ACTIVE,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            Contract.monthly_amount.is_not(None),  # type: ignore[union-attr]
        )
    ).one()
    plan_mrr_f = _f(plan_mrr)

    series = []
    for y, m in _months_back(months):
        fact = session.exec(
            select(func.coalesce(func.sum(Document.amount), 0))
            .join(Contract, Contract.id == Document.contract_id)
            .join(Organization, Organization.id == Document.organization_id)
            .where(
                _excl(),
                Document.doc_type == DocType.PAYMENT,
                Contract.contract_type == ContractType.SUBSCRIPTION,
                func.extract("year", Document.doc_date) == y,
                func.extract("month", Document.doc_date) == m,
            )
        ).one()
        series.append({
            "year": y,
            "month": m,
            "label": f"{m:02d}/{y}",
            "plan": plan_mrr_f,
            "fact": _f(fact),
            "ratio": round(_f(fact) / plan_mrr_f * 100, 1) if plan_mrr_f else None,
        })
    return series


# ----- /aging ----------------------------------------------------

@router.get("/aging")
def aging_buckets(session: Session = Depends(get_session)):
    """Buckets по просрочке: 0-30 / 31-60 / 61-90 / 90+ (в месяцах долга
    относительно monthly_ap)."""
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
        if months_overdue <= 1:
            key = "0-30"
        elif months_overdue <= 2:
            key = "31-60"
        elif months_overdue <= 3:
            key = "61-90"
        else:
            key = "90+"
        buckets[key].append(org)

    return [
        {
            "bucket": k,
            "amount": round(sum(_f(o.total_debt) for o in orgs_in), 2),
            "count": len(orgs_in),
        }
        for k, orgs_in in buckets.items()
    ]


@router.get("/aging/{bucket}")
def aging_bucket_detail(bucket: str, session: Session = Depends(get_session)):
    """Drill-down: список должников в конкретной aging-bucket для модалки."""
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
        if bucket == "0-30" and months_overdue > 1:
            continue
        if bucket == "31-60" and not (1 < months_overdue <= 2):
            continue
        if bucket == "61-90" and not (2 < months_overdue <= 3):
            continue
        if bucket == "90+" and months_overdue <= 3:
            continue
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


# ----- /mrr-trend (backward-compat) -----------------------------

@router.get("/mrr-trend")
def mrr_trend(session: Session = Depends(get_session)):
    results = session.exec(
        select(
            MonthlySnapshot.year,
            MonthlySnapshot.month,
            func.sum(MonthlySnapshot.sold_ap).label("sold_ap"),
            func.sum(MonthlySnapshot.paid_ap).label("paid_ap"),
        )
        .join(Organization, Organization.id == MonthlySnapshot.organization_id)
        .where(_excl())
        .group_by(MonthlySnapshot.year, MonthlySnapshot.month)
        .order_by(MonthlySnapshot.year, MonthlySnapshot.month)
    ).all()

    return [
        {
            "year": r[0], "month": r[1],
            "sold_ap": _f(r[2]), "paid_ap": _f(r[3]),
        }
        for r in results
    ]


# ----- /payment-matrix -------------------------------------------

@router.get("/payment-matrix")
def payment_matrix(months: int = 12, session: Session = Depends(get_session)):
    """Шахматка: organizations × months. Для каждой ячейки:
       plan (monthly_amount), fact (сумма PAYMENT в месяце), ratio.
       Возвращает компактный JSON для ECharts heatmap."""
    month_keys = _months_back(months)
    month_labels = [f"{m:02d}/{y}" for y, m in month_keys]
    y_min = month_keys[0][0]
    m_min = month_keys[0][1]
    cutoff = date(y_min, m_min, 1)

    # Активные подписочные клиенты с monthly_amount
    rows = session.exec(
        select(
            Organization.id,
            Organization.inn,
            Organization.name_display,
            Organization.name_1c,
            func.coalesce(func.sum(Contract.monthly_amount), 0).label("plan"),
        )
        .join(Contract, Contract.organization_id == Organization.id)
        .where(
            _excl(),
            Organization.status == OrgStatus.ACTIVE,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            Contract.status == ContractStatus.ACTIVE,
            Contract.monthly_amount.is_not(None),  # type: ignore[union-attr]
        )
        .group_by(Organization.id, Organization.inn, Organization.name_display, Organization.name_1c)
        .order_by(func.sum(Contract.monthly_amount).desc())
    ).all()

    org_ids = [r[0] for r in rows]
    if not org_ids:
        return {"months": month_labels, "orgs": [], "cells": []}

    # Один запрос: суммы PAYMENT по subscription-контрактам, сгруппированные по (org, year, month)
    pay_rows = session.exec(
        select(
            Document.organization_id,
            func.extract("year", Document.doc_date).label("y"),
            func.extract("month", Document.doc_date).label("m"),
            func.sum(Document.amount).label("paid"),
        )
        .join(Contract, Contract.id == Document.contract_id)
        .where(
            Document.doc_type == DocType.PAYMENT,
            Contract.contract_type == ContractType.SUBSCRIPTION,
            Document.organization_id.in_(org_ids),  # type: ignore[union-attr]
            Document.doc_date >= cutoff,
        )
        .group_by(Document.organization_id, "y", "m")
    ).all()
    paid_lookup = {(oid, int(y), int(m)): _f(p) for oid, y, m, p in pay_rows}

    orgs_out = []
    cells = []
    for oi, (org_id, inn, name_display, name_1c, plan) in enumerate(rows):
        plan_f = _f(plan)
        org_total_paid = 0.0
        for mi, (y, m) in enumerate(month_keys):
            paid = paid_lookup.get((org_id, y, m), 0.0)
            org_total_paid += paid
            ratio = round(paid / plan_f * 100, 0) if plan_f > 0 else None
            cells.append({
                "row": oi,
                "col": mi,
                "paid": round(paid, 2),
                "plan": round(plan_f, 2),
                "ratio": ratio,
            })
        orgs_out.append({
            "id": str(org_id),
            "inn": inn,
            "name": name_display or name_1c,
            "monthly_plan": round(plan_f, 2),
            "total_paid_period": round(org_total_paid, 2),
            "expected_period": round(plan_f * len(month_keys), 2),
        })

    return {
        "months": month_labels,
        "orgs": orgs_out,
        "cells": cells,
    }

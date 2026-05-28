"""CEO24 Dashboard API.

Все аналитические эндпоинты автоматически фильтруют организации с
excluded_from_analytics=True. Метрики сбора считаются из AR-леджера
(monthly_charges + payment_allocations), а не из сумм платежей по дате прихода."""

import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import (
    Alert,
    AlertStatus,
    Contract,
    DocType,
    Document,
    MonthlyCharge,
    MonthlySnapshot,
    Organization,
    OrgStatus,
    PaymentAllocation,
)
from app.services.aging import debt_aging
from app.services.dashboard_service import accrued_by_month as _accrued_by_month
from app.services.dashboard_service import collected_by_charge_month as _collected_by_charge_month
from app.services.dashboard_service import excl as _excl
from app.services.dashboard_service import first_pay_rows as _first_pay_rows_q
from app.services.dashboard_service import last_pay_rows as _last_pay_rows_q
from app.services.dashboard_service import months_back as _months_back
from app.services.dashboard_service import plan_mrr_total as _plan_mrr_total
from app.services.dashboard_service import to_float as _f

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)

_PAYMENTS_CONTRACT = "1C-PAYMENTS"


# --- эндпоинты --------------------------------------------------------------


@router.get("/summary")
def dashboard_summary(session: Session = Depends(get_session)):
    plan_mrr = _plan_mrr_total(session)

    today = date.today()
    prev_y, prev_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    prev2_y, prev2_m = (prev_y, prev_m - 1) if prev_m > 1 else (prev_y - 1, 12)

    collected = _collected_by_charge_month(session)
    accrued = _accrued_by_month(session)
    fact_mrr = collected.get((prev_y, prev_m), 0.0)
    fact_mrr_prev = collected.get((prev2_y, prev2_m), 0.0)

    mom_pct = None
    if fact_mrr_prev > 0:
        mom_pct = round((fact_mrr - fact_mrr_prev) / fact_mrr_prev * 100, 1)

    total_debt = _f(
        session.exec(
            select(func.coalesce(func.sum(Organization.total_debt), 0)).where(_excl())
        ).one()
    )

    # Долг по группам статусов (P3.0.3, вариант Б): «к взысканию» = ACTIVE+SUSPENDED,
    # «к списанию» = CHURNED+TRANSIT. PROSPECT исключаем — это шум.
    total_debt_active = _f(
        session.exec(
            select(func.coalesce(func.sum(Organization.total_debt), 0)).where(
                _excl(),
                Organization.status.in_(  # type: ignore[union-attr]
                    [OrgStatus.ACTIVE, OrgStatus.SUSPENDED]
                ),
            )
        ).one()
    )
    total_debt_writeoff = _f(
        session.exec(
            select(func.coalesce(func.sum(Organization.total_debt), 0)).where(
                _excl(),
                Organization.status.in_(  # type: ignore[union-attr]
                    [OrgStatus.CHURNED, OrgStatus.TRANSIT]
                ),
            )
        ).one()
    )

    active_clients = session.exec(
        select(func.count())
        .select_from(Organization)
        .where(_excl(), Organization.status == OrgStatus.ACTIVE)
    ).one()

    open_alerts = session.exec(
        select(func.count())
        .select_from(Alert)
        .join(Organization, Organization.id == Alert.organization_id)
        .where(_excl(), Alert.status == AlertStatus.OPEN)
    ).one()

    cutoff_30 = today - timedelta(days=30)
    cutoff_60 = today - timedelta(days=60)
    cutoff_90 = today - timedelta(days=90)

    new_30d = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id)
            .distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(_excl(), Document.doc_type == DocType.PAYMENT)
            .group_by(Document.organization_id)
            .having(func.min(Document.doc_date) >= cutoff_30)
            .subquery()
        )
    ).one()
    new_90d = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id)
            .distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(_excl(), Document.doc_type == DocType.PAYMENT)
            .group_by(Document.organization_id)
            .having(func.min(Document.doc_date) >= cutoff_90)
            .subquery()
        )
    ).one()

    paying_active = session.exec(
        select(Organization.id).where(
            _excl(),
            Organization.status == OrgStatus.ACTIVE,
            Organization.monthly_ap.is_not(None),  # type: ignore[union-attr]
            Organization.monthly_ap > 0,  # type: ignore[operator]
        )
    ).all()
    recently_paid_ids = set(
        session.exec(
            select(Document.organization_id)
            .distinct()
            .where(Document.doc_type == DocType.PAYMENT, Document.doc_date >= cutoff_60)
        ).all()
    )
    churned_60d = sum(1 for oid in paying_active if oid not in recently_paid_ids)

    # --- метрики клиентской базы --------------------------------------------
    year_start = date(today.year, 1, 1)
    first_pay_rows = _first_pay_rows_q(session)
    last_pay_rows = _last_pay_rows_q(session)
    new_paid_prev_month = sum(
        1 for _oid, d in first_pay_rows if d is not None and d.year == prev_y and d.month == prev_m
    )
    new_paid_curr_month = sum(
        1
        for _oid, d in first_pay_rows
        if d is not None and d.year == today.year and d.month == today.month
    )
    # новые за год: клиенты, чей первый платёж пришёлся на текущий год
    new_paid_curr_year = sum(
        1 for _oid, d in first_pay_rows if d is not None and d.year == today.year
    )
    # TRANSIT — юр.лица, переставшие платить (переоформление ИНН либо
    # транзитные плательщики за других клиентов). В отток их не учитываем.
    transit_ids = set(
        session.exec(select(Organization.id).where(Organization.status == OrgStatus.TRANSIT)).all()
    )
    # перестали платить с начала года: последний платёж в этом году, >60 дней назад
    stopped_since_year_start = sum(
        1
        for oid, d in last_pay_rows
        if d is not None and year_start <= d <= cutoff_60 and oid not in transit_ids
    )
    # база для churn rate — клиенты, у которых был платёж в прошлом году
    # (TRANSIT исключены — они не клиенты сами, а плательщики за других)
    paying_base = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id)
            .distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(
                _excl(),
                Document.doc_type == DocType.PAYMENT,
                Organization.status != OrgStatus.TRANSIT,
                func.extract("year", Document.doc_date) == today.year - 1,
            )
            .subquery()
        )
    ).one()
    churn_rate = round(stopped_since_year_start / paying_base * 100, 1) if paying_base else None

    # текущий (незакрытый) месяц — собрано за период из леджера
    cur_collected = collected.get((today.year, today.month), 0.0)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    # доля корзины 90+ — из той же логики, что и график «Структура долга»
    debt_90plus = sum(debt for _o, bucket, _age, debt in debt_aging(session) if bucket == "90+")
    debt_90plus_share = round(debt_90plus / total_debt * 100, 1) if total_debt else 0.0

    prev_accrued = accrued.get((prev_y, prev_m), 0.0)
    collection_rate_fact = round(fact_mrr / prev_accrued * 100, 1) if prev_accrued else None

    return {
        "mrr_fact": round(fact_mrr, 2),
        "mrr_plan": plan_mrr,
        "arr_plan": plan_mrr * 12,
        "total_debt": total_debt,
        "total_debt_active": total_debt_active,
        "total_debt_writeoff": total_debt_writeoff,
        "active_clients": active_clients,
        "open_alerts": open_alerts,
        "new_30d": new_30d,
        "new_90d": new_90d,
        "churned_60d": churned_60d,
        "new_paid_prev_month": new_paid_prev_month,
        "new_paid_curr_month": new_paid_curr_month,
        "new_paid_curr_year": new_paid_curr_year,
        "stopped_since_year_start": stopped_since_year_start,
        "churn_rate": churn_rate,
        "mom_mrr_delta_pct": mom_pct,
        "fact_month": f"{prev_y}-{prev_m:02d}",
        "mrr": round(fact_mrr, 2),
        "arr": plan_mrr * 12,
        "current_month_label": f"{today.year}-{today.month:02d}",
        "current_month_collected": round(cur_collected, 2),
        "days_passed": today.day,
        "days_in_month": days_in_month,
        "debt_90plus_amount": round(debt_90plus, 2),
        "debt_90plus_share": debt_90plus_share,
        "collection_rate_fact": collection_rate_fact,
    }


@router.get("/mrr-plan-vs-fact")
def mrr_plan_vs_fact(months: int = 12, session: Session = Depends(get_session)):
    plan_mrr = _plan_mrr_total(session)
    collected = _collected_by_charge_month(session)
    series = []
    for y, m in _months_back(months):
        fact = collected.get((y, m), 0.0)
        series.append(
            {
                "year": y,
                "month": m,
                "label": f"{m:02d}/{y}",
                "plan": plan_mrr,
                "fact": round(fact, 2),
                "ratio": round(fact / plan_mrr * 100, 1) if plan_mrr else None,
            }
        )
    return series


@router.get("/collection-trend")
def collection_trend(session: Session = Depends(get_session)):
    """Собираемость периода: за месяц M — accrued (Σ начислений) и collected
    (Σ аллокаций на начисления M, когда бы платёж ни пришёл). Только месяцы
    по текущий включительно — будущие авансовые начисления не показываются."""
    accrued = _accrued_by_month(session)
    collected = _collected_by_charge_month(session)
    today = date.today()
    cur = (today.year, today.month)
    out = []
    for y, m in sorted(k for k in accrued if k <= cur):
        a = accrued[(y, m)]
        c = collected.get((y, m), 0.0)
        out.append(
            {
                "year": y,
                "month": m,
                "label": f"{m:02d}/{y}",
                "accrued": round(a, 2),
                "collected": round(c, 2),
                "ratio": round(c / a * 100, 1) if a else None,
                "is_current_month": (y, m) == cur,
            }
        )
    return out


@router.get("/cash-inflow")
def cash_inflow(session: Session = Depends(get_session)):
    """Структура поступлений по месяцу прихода платежа: текущее / аванс /
    погашение долга / не определён / непериодические (непривязанные суммы)."""
    rows = session.exec(
        select(
            func.extract("year", Document.doc_date),
            func.extract("month", Document.doc_date),
            MonthlyCharge.year,
            MonthlyCharge.month,
            PaymentAllocation.allocated_amount,
        )
        .select_from(PaymentAllocation)
        .join(Document, Document.id == PaymentAllocation.payment_document_id)
        .join(Organization, Organization.id == Document.organization_id)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id, isouter=True)
        .where(_excl(), Document.doc_date.is_not(None))  # type: ignore[union-attr]
    ).all()

    def _empty() -> dict:
        return {
            "current": 0.0,
            "advance": 0.0,
            "arrears": 0.0,
            "undetermined": 0.0,
            "non_subscription": 0.0,
        }

    buckets: dict = {}
    for py, pm, cy, cm, amount in rows:
        key = (int(py), int(pm))
        b = buckets.setdefault(key, _empty())
        amt = _f(amount)
        if cy is None:
            b["undetermined"] += amt
        else:
            ck = (int(cy), int(cm))
            if ck == key:
                b["current"] += amt
            elif ck > key:
                b["advance"] += amt
            else:
                b["arrears"] += amt

    # непериодические = всего поступило − разнесено (по месяцу прихода)
    total_rows = session.exec(
        select(
            func.extract("year", Document.doc_date),
            func.extract("month", Document.doc_date),
            func.coalesce(func.sum(Document.amount), 0),
        )
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .join(Contract, Contract.id == Document.contract_id)
        .where(
            _excl(),
            Document.doc_type == DocType.PAYMENT,
            Document.doc_date.is_not(None),  # type: ignore[union-attr]
            Contract.contract_number == _PAYMENTS_CONTRACT,
        )
        .group_by(func.extract("year", Document.doc_date), func.extract("month", Document.doc_date))
    ).all()
    for py, pm, total in total_rows:
        key = (int(py), int(pm))
        b = buckets.setdefault(key, _empty())
        allocated = b["current"] + b["advance"] + b["arrears"] + b["undetermined"]
        b["non_subscription"] = max(_f(total) - allocated, 0.0)

    out = []
    for y, m in sorted(buckets):
        b = buckets[(y, m)]
        out.append(
            {
                "year": y,
                "month": m,
                "label": f"{m:02d}/{y}",
                **{k: round(v, 2) for k, v in b.items()},
            }
        )
    return out


_ALERT_META = {
    "large_debt": ("Крупная просрочка", "/debtors", 3),
    "non_payment": ("Неоплата", "/debtors", 3),
    "churn_risk": ("Риск ухода клиента", "/billing", 2),
    "collectability_drop": ("Падение собираемости", "/billing", 2),
    "project_overdue": ("Просрочка проекта", "/billing", 2),
    "anomaly": ("Аномалия в данных", "/billing", 2),
    "unassigned_client": ("Клиент без менеджера", "/billing", 1),
    "phantom_deal": ("Фантомная сделка", "/billing", 1),
    "new_client": ("Новый клиент", "/billing", 1),
}


@router.get("/attention")
def attention(session: Session = Depends(get_session)):
    """Открытые алерты, сгруппированные по типу. Для панели «Требуют внимания»."""
    rows = session.exec(
        select(
            Alert.alert_type,
            func.count().label("cnt"),
            func.coalesce(func.sum(Alert.metric_value), 0).label("amount"),
        )
        .where(Alert.status == AlertStatus.OPEN)
        .group_by(Alert.alert_type)
    ).all()
    out = []
    for alert_type, cnt, amount in rows:
        key = alert_type.value if hasattr(alert_type, "value") else str(alert_type)
        label, route, weight = _ALERT_META.get(key, (key, "/billing", 1))
        out.append(
            {
                "type": key,
                "label": label,
                "route": route,
                "count": int(cnt),
                "amount": _f(amount),
                "weight": weight,
            }
        )
    out.sort(key=lambda r: (-r["weight"], -r["amount"]))
    return out


@router.get("/aging")
def aging_buckets(session: Session = Depends(get_session)):
    """Структура долга по возрасту. Каждый клиент с долгом по 1С — ровно в
    одной корзине; сумма корзин равна суммарному долгу (плитка ДОЛГ)."""
    buckets = {"0-30": [0.0, 0], "31-60": [0.0, 0], "61-90": [0.0, 0], "90+": [0.0, 0]}
    for _o, bucket, _age, debt in debt_aging(session):
        buckets[bucket][0] += debt
        buckets[bucket][1] += 1
    return [{"bucket": k, "amount": round(v[0], 2), "count": v[1]} for k, v in buckets.items()]


@router.get("/aging/{bucket}")
def aging_bucket_detail(bucket: str, session: Session = Depends(get_session)):
    if bucket not in ("0-30", "31-60", "61-90", "90+"):
        raise HTTPException(status_code=400, detail="invalid bucket")
    rows = []
    for o, b, age, debt in debt_aging(session):
        if b != bucket:
            continue
        rows.append(
            {
                "inn": o.inn,
                "name": o.name_display or o.name_1c,
                "monthly_ap": _f(o.monthly_ap),
                "total_debt": round(debt, 2),
                "months_overdue": age,
                "status": o.status,
            }
        )
    rows.sort(key=lambda r: -r["total_debt"])
    return rows


@router.get("/mrr-trend")
def mrr_trend(
    forecast_months: int = 12,
    session: Session = Depends(get_session),
):
    """История MRR (sold/paid) + опциональный прогноз на N месяцев вперёд.

    Прогноз (P3.2): простая линейная регрессия по последним до 6 месяцам
    paid_ap. Этого достаточно для тренд-линии «куда идём», а не
    точечного прогноза. forecast_months=0 — прогноз не возвращать.
    """
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
    history = [
        {"year": r[0], "month": r[1], "sold_ap": _f(r[2]), "paid_ap": _f(r[3])} for r in results
    ]
    if forecast_months <= 0 or len(history) < 3:
        return history

    forecast = _forecast_mrr(history, forecast_months)
    return history + forecast


def _forecast_mrr(history: list[dict], months: int) -> list[dict]:
    """Линейная регрессия paid_ap по индексу месяца. Берём не больше 6
    последних точек (старее перестаёт отражать текущий тренд)."""
    pts = [
        (i, float(h["paid_ap"] or 0)) for i, h in enumerate(history) if h.get("paid_ap") is not None
    ]
    if len(pts) < 3:
        return []
    pts = pts[-6:]
    n = len(pts)
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        return []
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    last = history[-1]
    y, m = int(last["year"]), int(last["month"])
    out: list[dict] = []
    base_idx = len(history) - 1
    for k in range(1, months + 1):
        m += 1
        if m > 12:
            m = 1
            y += 1
        forecast_value = max(0.0, round(intercept + slope * (base_idx + k), 2))
        out.append(
            {
                "year": y,
                "month": m,
                "sold_ap": None,
                "paid_ap": None,
                "forecast_paid_ap": forecast_value,
            }
        )
    return out


@router.get("/payment-matrix")
def payment_matrix(year: int | None = None, session: Session = Depends(get_session)):
    """Шахматка: 12 месяцев календарного года (по умолчанию — текущего).

    Включает active клиентов с monthly_ap>0 и churned/transit клиентов,
    отключённых в выбранном году (churn_month попадает в [year-01-01..year-12-31]).
    """
    today = date.today()
    target_year = year or today.year
    month_keys = [(target_year, m) for m in range(1, 13)]
    month_labels = [f"{m:02d}/{target_year}" for _, m in month_keys]

    year_start = date(target_year, 1, 1)
    year_end = date(target_year, 12, 31)

    orgs = session.exec(
        select(Organization)
        .where(
            _excl(),
            (
                (
                    (Organization.status == OrgStatus.ACTIVE)
                    & (Organization.monthly_ap.is_not(None))  # type: ignore[union-attr]
                    & (Organization.monthly_ap > 0)  # type: ignore[operator]
                )
                | (
                    Organization.status.in_(  # type: ignore[union-attr]
                        [OrgStatus.CHURNED, OrgStatus.TRANSIT]
                    )
                    & (Organization.churn_month.is_not(None))  # type: ignore[union-attr]
                    & (Organization.churn_month >= year_start)  # type: ignore[operator]
                    & (Organization.churn_month <= year_end)  # type: ignore[operator]
                )
            ),
        )
        .order_by(Organization.monthly_ap.desc().nulls_last())  # type: ignore[union-attr]
    ).all()

    org_ids = [o.id for o in orgs]
    if not org_ids:
        return {"months": month_labels, "year": target_year, "orgs": [], "cells": []}

    pay_rows = session.exec(
        select(
            MonthlyCharge.organization_id,
            MonthlyCharge.year,
            MonthlyCharge.month,
            func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0),
        )
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .where(MonthlyCharge.organization_id.in_(org_ids))  # type: ignore[union-attr]
        .group_by(MonthlyCharge.organization_id, MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    paid_lookup = {(oid, int(y), int(m)): _f(p) for oid, y, m, p in pay_rows}

    orgs_out, cells = [], []
    for oi, org in enumerate(orgs):
        plan = _f(org.monthly_ap) if org.monthly_ap else 0.0
        churn_col: int | None = None
        if org.churn_month and year_start <= org.churn_month <= year_end:
            churn_col = org.churn_month.month - 1

        total_paid = 0.0
        for mi, (y, m) in enumerate(month_keys):
            paid = paid_lookup.get((org.id, y, m), 0.0)
            total_paid += paid
            ratio = round(paid / plan * 100, 0) if plan > 0 else None
            cells.append(
                {
                    "row": oi,
                    "col": mi,
                    "paid": round(paid, 2),
                    "plan": round(plan, 2),
                    "ratio": ratio,
                }
            )
        orgs_out.append(
            {
                "id": str(org.id),
                "inn": org.inn,
                "name": org.name_display or org.name_1c,
                "status": org.status.value if hasattr(org.status, "value") else org.status,
                "churn_col": churn_col,
                "churn_month": org.churn_month.isoformat() if org.churn_month else None,
                "monthly_plan": round(plan, 2),
                "total_paid_period": round(total_paid, 2),
                "expected_period": round(plan * len(month_keys), 2),
            }
        )

    return {
        "months": month_labels,
        "year": target_year,
        "orgs": orgs_out,
        "cells": cells,
    }

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

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)

_PAYMENTS_CONTRACT = "1C-PAYMENTS"


def _excl():
    return Organization.excluded_from_analytics == False  # noqa: E712


def _months_back(n: int) -> list[tuple[int, int]]:
    today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def _f(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def _plan_mrr_total(session: Session) -> float:
    """План MRR: сумма Organization.monthly_ap по активным клиентам."""
    v = session.exec(
        select(func.coalesce(func.sum(Organization.monthly_ap), 0))
        .where(_excl(), Organization.status == OrgStatus.ACTIVE)
    ).one()
    return _f(v)


# --- AR-леджер: начисления и сбор -------------------------------------------

def _accrued_by_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ начислений (monthly_charge.amount) по месяцам, неисключённые клиенты."""
    rows = session.exec(
        select(MonthlyCharge.year, MonthlyCharge.month,
               func.coalesce(func.sum(MonthlyCharge.amount), 0))
        .select_from(MonthlyCharge)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(_excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): _f(s) for y, m, s in rows}


def _collected_by_charge_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ аллокаций по месяцу НАЧИСЛЕНИЯ — сколько собрано за период."""
    rows = session.exec(
        select(MonthlyCharge.year, MonthlyCharge.month,
               func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(_excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): _f(s) for y, m, s in rows}


def _ledger_outstanding(session: Session) -> dict:
    """{org_id: {(year, month): outstanding}} — непокрытый остаток начислений
    для неисключённых клиентов."""
    charges = session.exec(
        select(MonthlyCharge)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(_excl())
    ).all()
    alloc_rows = session.exec(
        select(PaymentAllocation.monthly_charge_id,
               func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .where(PaymentAllocation.monthly_charge_id.is_not(None))  # type: ignore[union-attr]
        .group_by(PaymentAllocation.monthly_charge_id)
    ).all()
    allocated = {cid: _f(s) for cid, s in alloc_rows}
    out: dict = {}
    for c in charges:
        left = _f(c.amount) - allocated.get(c.id, 0.0)
        out.setdefault(c.organization_id, {})[(c.year, c.month)] = left
    return out


def _age_bucket(age_months: int) -> str:
    if age_months <= 0:
        return "0-30"
    if age_months == 1:
        return "31-60"
    if age_months == 2:
        return "61-90"
    return "90+"


def _debt_aging(session: Session) -> list[tuple]:
    """Структура долга: каждый клиент с долгом по 1С попадает РОВНО в одну
    корзину. Возраст долга — число календарных месяцев от самого раннего
    неоплаченного начисления леджера (АП начисляется 1-го числа месяца).
    Сумма в корзине — долг клиента из 1С (`total_debt`), поэтому итог по
    корзинам сходится с плиткой ДОЛГ. Возвращает [(org, bucket, age, debt)]."""
    today = date.today()
    cur_idx = today.year * 12 + today.month
    debtors = session.exec(
        select(Organization).where(
            _excl(),
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()
    outstanding = _ledger_outstanding(session)
    rows: list[tuple] = []
    for o in debtors:
        periods = outstanding.get(o.id, {})
        unpaid = [(y, m) for (y, m), left in periods.items()
                  if left > 0.01 and y * 12 + m <= cur_idx]
        if unpaid:
            oy, om = min(unpaid)
            age = cur_idx - (oy * 12 + om)
        else:
            # 1С показывает долг, но непокрытых начислений в леджере нет —
            # оцениваем возраст по отношению долг/АП
            monthly = _f(o.monthly_ap)
            age = int(_f(o.total_debt) / monthly) if monthly > 0 else 3
        rows.append((o, _age_bucket(age), age, _f(o.total_debt)))
    return rows


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

    new_30d = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id).distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(_excl(), Document.doc_type == DocType.PAYMENT)
            .group_by(Document.organization_id)
            .having(func.min(Document.doc_date) >= cutoff_30)
            .subquery()
        )
    ).one()
    new_90d = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id).distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(_excl(), Document.doc_type == DocType.PAYMENT)
            .group_by(Document.organization_id)
            .having(func.min(Document.doc_date) >= cutoff_90)
            .subquery()
        )
    ).one()

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

    # --- метрики клиентской базы --------------------------------------------
    year_start = date(today.year, 1, 1)
    first_pay_rows = session.exec(
        select(Document.organization_id, func.min(Document.doc_date))
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .where(_excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by(Document.organization_id)
    ).all()
    last_pay_rows = session.exec(
        select(Document.organization_id, func.max(Document.doc_date))
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .where(_excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by(Document.organization_id)
    ).all()
    new_paid_prev_month = sum(
        1 for _oid, d in first_pay_rows
        if d is not None and d.year == prev_y and d.month == prev_m
    )
    new_paid_curr_month = sum(
        1 for _oid, d in first_pay_rows
        if d is not None and d.year == today.year and d.month == today.month
    )
    # перестали платить с начала года: последний платёж в этом году, >60 дней назад
    stopped_since_year_start = sum(
        1 for _oid, d in last_pay_rows
        if d is not None and year_start <= d <= cutoff_60
    )
    # база для churn rate — клиенты, у которых был платёж в прошлом году
    paying_base = session.exec(
        select(func.count()).select_from(
            select(Document.organization_id).distinct()
            .join(Organization, Organization.id == Document.organization_id)
            .where(_excl(), Document.doc_type == DocType.PAYMENT,
                   func.extract("year", Document.doc_date) == today.year - 1)
            .subquery()
        )
    ).one()
    churn_rate = (round(stopped_since_year_start / paying_base * 100, 1)
                  if paying_base else None)

    # текущий (незакрытый) месяц — собрано за период из леджера
    cur_collected = collected.get((today.year, today.month), 0.0)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    # доля корзины 90+ — из той же логики, что и график «Структура долга»
    debt_90plus = sum(
        debt for _o, bucket, _age, debt in _debt_aging(session)
        if bucket == "90+"
    )
    debt_90plus_share = round(debt_90plus / total_debt * 100, 1) if total_debt else 0.0

    prev_accrued = accrued.get((prev_y, prev_m), 0.0)
    collection_rate_fact = round(fact_mrr / prev_accrued * 100, 1) if prev_accrued else None

    return {
        "mrr_fact": round(fact_mrr, 2),
        "mrr_plan": plan_mrr,
        "arr_plan": plan_mrr * 12,
        "total_debt": total_debt,
        "active_clients": active_clients,
        "open_alerts": open_alerts,
        "new_30d": new_30d,
        "new_90d": new_90d,
        "churned_60d": churned_60d,
        "new_paid_prev_month": new_paid_prev_month,
        "new_paid_curr_month": new_paid_curr_month,
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
        series.append({
            "year": y, "month": m, "label": f"{m:02d}/{y}",
            "plan": plan_mrr, "fact": round(fact, 2),
            "ratio": round(fact / plan_mrr * 100, 1) if plan_mrr else None,
        })
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
    for (y, m) in sorted(k for k in accrued if k <= cur):
        a = accrued[(y, m)]
        c = collected.get((y, m), 0.0)
        out.append({
            "year": y, "month": m, "label": f"{m:02d}/{y}",
            "accrued": round(a, 2), "collected": round(c, 2),
            "ratio": round(c / a * 100, 1) if a else None,
            "is_current_month": (y, m) == cur,
        })
    return out


@router.get("/cash-inflow")
def cash_inflow(session: Session = Depends(get_session)):
    """Структура поступлений по месяцу прихода платежа: текущее / аванс /
    погашение долга / не определён / непериодические (непривязанные суммы)."""
    rows = session.exec(
        select(
            func.extract("year", Document.doc_date),
            func.extract("month", Document.doc_date),
            MonthlyCharge.year, MonthlyCharge.month,
            PaymentAllocation.allocated_amount,
        )
        .select_from(PaymentAllocation)
        .join(Document, Document.id == PaymentAllocation.payment_document_id)
        .join(Organization, Organization.id == Document.organization_id)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id,
              isouter=True)
        .where(_excl(), Document.doc_date.is_not(None))  # type: ignore[union-attr]
    ).all()

    def _empty() -> dict:
        return {"current": 0.0, "advance": 0.0, "arrears": 0.0,
                "undetermined": 0.0, "non_subscription": 0.0}

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
        .where(_excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None),  # type: ignore[union-attr]
               Contract.contract_number == _PAYMENTS_CONTRACT)
        .group_by(func.extract("year", Document.doc_date),
                  func.extract("month", Document.doc_date))
    ).all()
    for py, pm, total in total_rows:
        key = (int(py), int(pm))
        b = buckets.setdefault(key, _empty())
        allocated = b["current"] + b["advance"] + b["arrears"] + b["undetermined"]
        b["non_subscription"] = max(_f(total) - allocated, 0.0)

    out = []
    for (y, m) in sorted(buckets):
        b = buckets[(y, m)]
        out.append({"year": y, "month": m, "label": f"{m:02d}/{y}",
                    **{k: round(v, 2) for k, v in b.items()}})
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
        out.append({
            "type": key, "label": label, "route": route,
            "count": int(cnt), "amount": _f(amount), "weight": weight,
        })
    out.sort(key=lambda r: (-r["weight"], -r["amount"]))
    return out


@router.get("/aging")
def aging_buckets(session: Session = Depends(get_session)):
    """Структура долга по возрасту. Каждый клиент с долгом по 1С — ровно в
    одной корзине; сумма корзин равна суммарному долгу (плитка ДОЛГ)."""
    buckets = {"0-30": [0.0, 0], "31-60": [0.0, 0],
               "61-90": [0.0, 0], "90+": [0.0, 0]}
    for _o, bucket, _age, debt in _debt_aging(session):
        buckets[bucket][0] += debt
        buckets[bucket][1] += 1
    return [
        {"bucket": k, "amount": round(v[0], 2), "count": v[1]}
        for k, v in buckets.items()
    ]


@router.get("/aging/{bucket}")
def aging_bucket_detail(bucket: str, session: Session = Depends(get_session)):
    if bucket not in ("0-30", "31-60", "61-90", "90+"):
        raise HTTPException(status_code=400, detail="invalid bucket")
    rows = []
    for o, b, age, debt in _debt_aging(session):
        if b != bucket:
            continue
        rows.append({
            "inn": o.inn,
            "name": o.name_display or o.name_1c,
            "monthly_ap": _f(o.monthly_ap),
            "total_debt": round(debt, 2),
            "months_overdue": age,
            "status": o.status,
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
    return [
        {"year": r[0], "month": r[1], "sold_ap": _f(r[2]), "paid_ap": _f(r[3])}
        for r in results
    ]


@router.get("/payment-matrix")
def payment_matrix(months: int = 12, session: Session = Depends(get_session)):
    """Шахматка: ряд на клиента с monthly_ap > 0, колонки — месяцы.
    План = Organization.monthly_ap. Факт = Σ аллокаций на начисление месяца."""
    month_keys = _months_back(months)
    month_labels = [f"{m:02d}/{y}" for y, m in month_keys]

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
            MonthlyCharge.organization_id,
            MonthlyCharge.year, MonthlyCharge.month,
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

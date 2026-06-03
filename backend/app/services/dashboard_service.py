"""Общие helpers расчёта KPI дашборда.

Вынесено из app/api/v1/dashboard.py, чтобы dashboard и composition_service
считали из одних функций — гарантия совпадения цифр на плитках и в drill-down."""

import uuid
from datetime import date, timedelta

from sqlalchemy import and_
from sqlmodel import Session, func, select

from app.models import (
    DocType,
    Document,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
)


def excl():
    """Предикат: организация не исключена из аналитики.

    Включает два условия:
      - `excluded_from_analytics=False` — старый флаг (тестовые/дублёры);
      - `status != SUPPLIER` — поставщики (P3.0.8a, возвраты на расчётный
        счёт). Софья 2026-05-29: «полностью исключаем из CEO-дашборда».
    """
    return and_(
        Organization.excluded_from_analytics == False,  # noqa: E712
        Organization.status != OrgStatus.SUPPLIER,
    )


def to_float(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def plan_mrr_total(session: Session) -> float:
    """План MRR: Σ monthly_ap по активным неисключённым клиентам."""
    v = session.exec(
        select(func.coalesce(func.sum(Organization.monthly_ap), 0)).where(
            excl(), Organization.status == OrgStatus.ACTIVE
        )
    ).one()
    return to_float(v)


def accrued_by_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ начислений по месяцам, неисключённые клиенты."""
    rows = session.exec(
        select(
            MonthlyCharge.year,
            MonthlyCharge.month,
            func.coalesce(func.sum(MonthlyCharge.amount), 0),
        )
        .select_from(MonthlyCharge)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): to_float(s) for y, m, s in rows}


def collected_by_charge_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ аллокаций по месяцу начисления — сколько собрано за период."""
    rows = session.exec(
        select(
            MonthlyCharge.year,
            MonthlyCharge.month,
            func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0),
        )
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): to_float(s) for y, m, s in rows}


def first_pay_rows(session: Session) -> list[tuple]:
    """[(org_id, min_doc_date)] для неисключённых клиентов с платежами."""
    return list(
        session.exec(
            select(Document.organization_id, func.min(Document.doc_date))
            .select_from(Document)
            .join(Organization, Organization.id == Document.organization_id)
            .where(excl(), Document.doc_type == DocType.PAYMENT, Document.doc_date.is_not(None))  # type: ignore[union-attr]
            .group_by(Document.organization_id)
        ).all()
    )


def last_pay_rows(session: Session) -> list[tuple]:
    """[(org_id, max_doc_date)] для неисключённых клиентов с платежами."""
    return list(
        session.exec(
            select(Document.organization_id, func.max(Document.doc_date))
            .select_from(Document)
            .join(Organization, Organization.id == Document.organization_id)
            .where(excl(), Document.doc_type == DocType.PAYMENT, Document.doc_date.is_not(None))  # type: ignore[union-attr]
            .group_by(Document.organization_id)
        ).all()
    )


def max_covered_month(session: Session) -> dict[uuid.UUID, tuple[int, int]]:
    """Для каждого клиента — последний полностью оплаченный месяц начисления.

    «Полностью оплачен» = Σ аллокаций на charge ≥ его суммы. Берём максимум
    по таким месяцам. Это и есть «оплачено по месяц X» — позволяет отличить
    клиента, оплатившего на месяцы вперёд (covered ≥ текущего), от ушедшего
    (покрытие заканчивается в прошлом)."""
    rows = session.exec(
        select(
            MonthlyCharge.organization_id,
            MonthlyCharge.year,
            MonthlyCharge.month,
            MonthlyCharge.amount,
            func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0),
        )
        .select_from(MonthlyCharge)
        .join(
            PaymentAllocation,
            PaymentAllocation.monthly_charge_id == MonthlyCharge.id,
            isouter=True,
        )
        .group_by(
            MonthlyCharge.organization_id,
            MonthlyCharge.id,
            MonthlyCharge.year,
            MonthlyCharge.month,
            MonthlyCharge.amount,
        )
    ).all()
    out: dict[uuid.UUID, tuple[int, int]] = {}
    for oid, y, m, amount, allocated in rows:
        amt = to_float(amount)
        if amt <= 0 or to_float(allocated) < amt - 0.01:
            continue  # начисление не закрыто полностью
        key = (int(y), int(m))
        if oid not in out or key > out[oid]:
            out[oid] = key
    return out


def prepaid_current_ids(session: Session, today: date | None = None) -> set[uuid.UUID]:
    """id клиентов, у кого подписка оплачена по текущий месяц или вперёд.

    Такие клиенты не считаются «перестали платить / отток», даже если
    последний платёж пришёл давно (оплата на полгода-год вперёд — частый
    кейс, см. замечание Софьи 2026-06-02 по составу оттока)."""
    if today is None:
        today = date.today()
    cur = (today.year, today.month)
    return {oid for oid, mm in max_covered_month(session).items() if mm >= cur}


def churned_this_year_ids(session: Session, today: date | None = None) -> set[uuid.UUID]:
    """Отток с начала года — статус-driven (выверено вручную по 1С).

    Только клиенты со статусом `CHURNED` и месяцем отключения в этом году.
    Машина не может отличить «ушёл» от «активный должник» по дате платежа —
    это решает Софья при сверке транзакций в 1С (решение CEO 2026-06-03,
    ADR-024). Авто-детект просрочки — отдельный сигнал `active_overdue_ids`."""
    if today is None:
        today = date.today()
    year_start = date(today.year, 1, 1)
    return set(
        session.exec(
            select(Organization.id).where(
                excl(),
                Organization.status == OrgStatus.CHURNED,
                Organization.churn_month.is_not(None),  # type: ignore[union-attr]
                Organization.churn_month >= year_start,  # type: ignore[operator]
            )
        ).all()
    )


def active_overdue_ids(session: Session, today: date | None = None) -> set[uuid.UUID]:
    """Активные клиенты с просрочкой оплаты (сигнал для взыскания, не отток).

    Статус ACTIVE, есть АП, последний платёж в этом году но >60 дней назад,
    подписка НЕ оплачена вперёд. PROSPECT/TRANSIT/SUPPLIER/CHURNED сюда не
    попадают (только ACTIVE). Это бывший авто-детект «перестали платить» —
    после решения CEO он больше не называется оттоком (ADR-024)."""
    if today is None:
        today = date.today()
    year_start = date(today.year, 1, 1)
    cutoff_60 = today - timedelta(days=60)
    active_ids = set(
        session.exec(
            select(Organization.id).where(
                excl(),
                Organization.status == OrgStatus.ACTIVE,
                Organization.monthly_ap.is_not(None),  # type: ignore[union-attr]
                Organization.monthly_ap > 0,  # type: ignore[operator]
            )
        ).all()
    )
    if not active_ids:
        return set()
    last_pay = dict(last_pay_rows(session))  # уже отфильтровано excl()
    prepaid = prepaid_current_ids(session, today)
    return {
        oid
        for oid, d in last_pay.items()
        if oid in active_ids
        and d is not None
        and year_start <= d <= cutoff_60
        and oid not in prepaid
    }


def months_back(n: int, today: date | None = None) -> list[tuple[int, int]]:
    """Список последних n месяцев в порядке от старого к новому."""
    if today is None:
        today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))

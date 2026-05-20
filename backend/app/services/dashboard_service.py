"""Общие helpers расчёта KPI дашборда.

Вынесено из app/api/v1/dashboard.py, чтобы dashboard и composition_service
считали из одних функций — гарантия совпадения цифр на плитках и в drill-down."""
from datetime import date

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
    """Предикат: организация не исключена из аналитики."""
    return Organization.excluded_from_analytics == False  # noqa: E712


def to_float(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def plan_mrr_total(session: Session) -> float:
    """План MRR: Σ monthly_ap по активным неисключённым клиентам."""
    v = session.exec(
        select(func.coalesce(func.sum(Organization.monthly_ap), 0))
        .where(excl(), Organization.status == OrgStatus.ACTIVE)
    ).one()
    return to_float(v)


def accrued_by_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ начислений по месяцам, неисключённые клиенты."""
    rows = session.exec(
        select(MonthlyCharge.year, MonthlyCharge.month,
               func.coalesce(func.sum(MonthlyCharge.amount), 0))
        .select_from(MonthlyCharge)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): to_float(s) for y, m, s in rows}


def collected_by_charge_month(session: Session) -> dict[tuple[int, int], float]:
    """Σ аллокаций по месяцу начисления — сколько собрано за период."""
    rows = session.exec(
        select(MonthlyCharge.year, MonthlyCharge.month,
               func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .select_from(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(excl())
        .group_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    return {(int(y), int(m)): to_float(s) for y, m, s in rows}


def first_pay_rows(session: Session) -> list[tuple]:
    """[(org_id, min_doc_date)] для неисключённых клиентов с платежами."""
    return list(session.exec(
        select(Document.organization_id, func.min(Document.doc_date))
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .where(excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by(Document.organization_id)
    ).all())


def last_pay_rows(session: Session) -> list[tuple]:
    """[(org_id, max_doc_date)] для неисключённых клиентов с платежами."""
    return list(session.exec(
        select(Document.organization_id, func.max(Document.doc_date))
        .select_from(Document)
        .join(Organization, Organization.id == Document.organization_id)
        .where(excl(), Document.doc_type == DocType.PAYMENT,
               Document.doc_date.is_not(None))  # type: ignore[union-attr]
        .group_by(Document.organization_id)
    ).all())


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

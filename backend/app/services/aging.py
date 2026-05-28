"""Возраст и корзина долга — единая логика для дашборда, реестра должников
и модуля отчётов.

Возраст долга клиента = число календарных месяцев от самого раннего
неоплаченного начисления леджера (АП начисляется 1-го числа месяца).
Сумма долга берётся из 1С (`Organization.total_debt`), каждый клиент
попадает ровно в одну корзину."""

from datetime import date

from sqlmodel import Session, func, select

from app.models import MonthlyCharge, Organization, PaymentAllocation


def age_bucket(age_months: int) -> str:
    """Календарный возраст (в месяцах) → корзина."""
    if age_months <= 0:
        return "0-30"
    if age_months == 1:
        return "31-60"
    if age_months == 2:
        return "61-90"
    return "90+"


def ledger_outstanding(session: Session) -> dict:
    """{org_id: {(year, month): outstanding}} — непокрытый остаток начислений
    для неисключённых клиентов."""
    charges = session.exec(
        select(MonthlyCharge)
        .join(Organization, Organization.id == MonthlyCharge.organization_id)
        .where(Organization.excluded_from_analytics == False)  # noqa: E712
    ).all()
    alloc_rows = session.exec(
        select(
            PaymentAllocation.monthly_charge_id,
            func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0),
        )
        .where(PaymentAllocation.monthly_charge_id.is_not(None))  # type: ignore[union-attr]
        .group_by(PaymentAllocation.monthly_charge_id)
    ).all()
    allocated = {cid: float(s) for cid, s in alloc_rows}
    out: dict = {}
    for c in charges:
        left = float(c.amount or 0) - allocated.get(c.id, 0.0)
        out.setdefault(c.organization_id, {})[(c.year, c.month)] = left
    return out


def debt_aging(session: Session) -> list[tuple]:
    """[(org, bucket, age_months, debt)] — для всех неисключённых клиентов
    с долгом по 1С. Каждый клиент учитывается ровно один раз.

    Возраст = календарные месяцы от самого раннего неоплаченного начисления.
    Если в леджере непокрытых начислений нет (1С показывает долг, а леджер
    пуст) — возраст оценивается по отношению долг/АП."""
    today = date.today()
    cur_idx = today.year * 12 + today.month
    debtors = session.exec(
        select(Organization).where(
            Organization.excluded_from_analytics == False,  # noqa: E712
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()
    outstanding = ledger_outstanding(session)
    rows: list[tuple] = []
    for o in debtors:
        periods = outstanding.get(o.id, {})
        unpaid = [
            (y, m) for (y, m), left in periods.items() if left > 0.01 and y * 12 + m <= cur_idx
        ]
        if unpaid:
            oy, om = min(unpaid)
            age = cur_idx - (oy * 12 + om)
        else:
            monthly = float(o.monthly_ap or 0)
            age = int(float(o.total_debt or 0) / monthly) if monthly > 0 else 3
        rows.append((o, age_bucket(age), age, float(o.total_debt or 0)))
    return rows


def aging_index(session: Session) -> dict:
    """{org_id: (bucket, age_months)} — для точечного lookup по клиенту."""
    return {o.id: (bucket, age) for o, bucket, age, _debt in debt_aging(session)}

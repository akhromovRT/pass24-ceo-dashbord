"""Регресс: helpers, вынесенные из dashboard.py, ведут себя как раньше."""

from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session

from app.models import (
    AllocationBasis,
    ChargeSource,
    Contract,
    ContractType,
    DocType,
    Document,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
)
from app.services.dashboard_service import (
    collected_by_charge_month,
    first_pay_rows,
    last_pay_rows,
    max_covered_month,
    plan_mrr_total,
    prepaid_current_ids,
    stopped_since_year_start_ids,
)


def _org(session, inn, **kw):
    org = Organization(inn=inn, name_1c=kw.pop("name", "X"), **kw)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _charge(session, org, year, month, amount):
    c = MonthlyCharge(
        organization_id=org.id,
        year=year,
        month=month,
        amount=Decimal(str(amount)),
        source=ChargeSource.SYNTHETIC_TARIFF,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _pay(session, org, charge, amount, pay_date):
    contract = Contract(organization_id=org.id, contract_type=ContractType.SUBSCRIPTION)
    session.add(contract)
    session.commit()
    session.refresh(contract)
    doc = Document(
        contract_id=contract.id,
        organization_id=org.id,
        doc_type=DocType.PAYMENT,
        doc_date=pay_date,
        amount=Decimal(str(amount)),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    alloc = PaymentAllocation(
        payment_document_id=doc.id,
        monthly_charge_id=charge.id,
        allocated_amount=Decimal(str(amount)),
        basis=AllocationBasis.EXPLICIT_PERIOD,
    )
    session.add(alloc)
    session.commit()


def test_plan_mrr_total_sums_active_ap(db_session: Session):
    _org(db_session, "1", status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    _org(db_session, "2", status=OrgStatus.ACTIVE, monthly_ap=Decimal("5000"))
    _org(db_session, "3", status=OrgStatus.CHURNED, monthly_ap=Decimal("999"))
    _org(
        db_session,
        "4",
        status=OrgStatus.ACTIVE,
        monthly_ap=Decimal("1000"),
        excluded_from_analytics=True,
    )
    assert plan_mrr_total(db_session) == 15000.0


def test_collected_by_charge_month(db_session: Session):
    org = _org(db_session, "10", status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    ch = _charge(db_session, org, 2026, 4, 10000)
    _pay(db_session, org, ch, 10000, date(2026, 4, 5))
    out = collected_by_charge_month(db_session)
    assert out[(2026, 4)] == 10000.0


def test_first_and_last_pay_rows(db_session: Session):
    org = _org(db_session, "20", status=OrgStatus.ACTIVE)
    ch = _charge(db_session, org, 2026, 1, 5000)
    _pay(db_session, org, ch, 5000, date(2026, 1, 10))
    _pay(db_session, org, ch, 3000, date(2026, 3, 20))
    first = dict(first_pay_rows(db_session))
    last = dict(last_pay_rows(db_session))
    assert first[org.id] == date(2026, 1, 10)
    assert last[org.id] == date(2026, 3, 20)


# --- prepayment-aware churn (Софья 2026-06-02) ------------------------------


def test_max_covered_month_takes_latest_fully_paid(db_session: Session):
    org = _org(db_session, "30", status=OrgStatus.ACTIVE)
    ch1 = _charge(db_session, org, 2026, 1, 1000)
    ch2 = _charge(db_session, org, 2026, 2, 1000)
    ch3 = _charge(db_session, org, 2026, 3, 1000)
    _pay(db_session, org, ch1, 1000, date(2026, 1, 5))
    _pay(db_session, org, ch2, 1000, date(2026, 1, 5))
    _pay(db_session, org, ch3, 400, date(2026, 1, 5))  # частично — не считается
    assert max_covered_month(db_session)[org.id] == (2026, 2)


def test_prepaid_current_ids_excludes_lapsed_includes_prepaid(db_session: Session):
    today = date.today()
    cur = (today.year, today.month)
    nxt_y, nxt_m = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)

    prepaid = _org(db_session, "40", status=OrgStatus.ACTIVE)
    ch_future = _charge(db_session, prepaid, nxt_y, nxt_m, 1000)
    _pay(db_session, prepaid, ch_future, 1000, date(today.year, 1, 5))  # оплатил вперёд

    lapsed = _org(db_session, "41", status=OrgStatus.ACTIVE)
    ch_old = _charge(db_session, lapsed, 2025, 1, 1000)
    _pay(db_session, lapsed, ch_old, 1000, date(2025, 1, 5))  # покрытие в прошлом

    ids = prepaid_current_ids(db_session, today)
    assert prepaid.id in ids
    assert lapsed.id not in ids
    # текущий месяц тоже засчитывается как «оплачено вперёд/по текущий»
    cur_org = _org(db_session, "42", status=OrgStatus.ACTIVE)
    ch_cur = _charge(db_session, cur_org, cur[0], cur[1], 1000)
    _pay(db_session, cur_org, ch_cur, 1000, date(today.year, 1, 5))
    assert cur_org.id in prepaid_current_ids(db_session, today)


def test_stopped_excludes_prepaid_clients(db_session: Session):
    """Кейс Кутузовской Ривьеры: последний платёж давно, но оплачено вперёд."""
    today = date.today()
    year_start = date(today.year, 1, 1)
    long_ago = today - timedelta(days=70)
    if long_ago < year_start:
        return  # в начале года кейс не воспроизводится — пропускаем

    prepaid = _org(db_session, "50", name="Prepaid", status=OrgStatus.ACTIVE)
    ch_cur = _charge(db_session, prepaid, today.year, today.month, 1000)
    _pay(db_session, prepaid, ch_cur, 1000, long_ago)  # оплатил текущий месяц давно

    truly_stopped = _org(db_session, "51", name="Stopped", status=OrgStatus.ACTIVE)
    ch_old = _charge(db_session, truly_stopped, long_ago.year, long_ago.month, 1000)
    _pay(db_session, truly_stopped, ch_old, 1000, long_ago)

    ids = stopped_since_year_start_ids(db_session, today)
    assert prepaid.id not in ids  # предоплата вперёд — не отток
    assert truly_stopped.id in ids


def test_stopped_includes_manual_churned_this_year(db_session: Session):
    today = date.today()
    churned = _org(
        db_session,
        "60",
        name="Manual",
        status=OrgStatus.CHURNED,
        churn_month=date(today.year, 1, 1),
    )
    ids = stopped_since_year_start_ids(db_session, today)
    assert churned.id in ids

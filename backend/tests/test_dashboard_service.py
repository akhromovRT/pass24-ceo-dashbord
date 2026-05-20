"""Регресс: helpers, вынесенные из dashboard.py, ведут себя как раньше."""
from datetime import date
from decimal import Decimal

from sqlmodel import Session

from app.models import (
    AllocationBasis, ChargeSource, Contract, ContractType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation,
)
from app.services.dashboard_service import (
    collected_by_charge_month,
    first_pay_rows,
    last_pay_rows,
    plan_mrr_total,
)


def _org(session, inn, **kw):
    org = Organization(inn=inn, name_1c=kw.pop("name", "X"), **kw)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _charge(session, org, year, month, amount):
    c = MonthlyCharge(organization_id=org.id, year=year, month=month,
                      amount=Decimal(str(amount)),
                      source=ChargeSource.SYNTHETIC_TARIFF)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _pay(session, org, charge, amount, pay_date):
    contract = Contract(organization_id=org.id,
                        contract_type=ContractType.SUBSCRIPTION)
    session.add(contract)
    session.commit()
    session.refresh(contract)
    doc = Document(contract_id=contract.id, organization_id=org.id,
                   doc_type=DocType.PAYMENT, doc_date=pay_date,
                   amount=Decimal(str(amount)))
    session.add(doc)
    session.commit()
    session.refresh(doc)
    alloc = PaymentAllocation(payment_document_id=doc.id,
                              monthly_charge_id=charge.id,
                              allocated_amount=Decimal(str(amount)),
                              basis=AllocationBasis.EXPLICIT_PERIOD)
    session.add(alloc)
    session.commit()


def test_plan_mrr_total_sums_active_ap(db_session: Session):
    _org(db_session, "1", status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    _org(db_session, "2", status=OrgStatus.ACTIVE, monthly_ap=Decimal("5000"))
    _org(db_session, "3", status=OrgStatus.CHURNED, monthly_ap=Decimal("999"))
    _org(db_session, "4", status=OrgStatus.ACTIVE, monthly_ap=Decimal("1000"),
         excluded_from_analytics=True)
    assert plan_mrr_total(db_session) == 15000.0


def test_collected_by_charge_month(db_session: Session):
    org = _org(db_session, "10", status=OrgStatus.ACTIVE,
               monthly_ap=Decimal("10000"))
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

"""Unit-тесты builder'а composition по каждой метрике."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session

from app.models import (
    AllocationBasis, ChargeSource, Contract, ContractType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation,
)
from app.services.composition_service import (
    build_composition_report,
    control_value_for,
)
from app.services.report_service import ReportCriteria


def _org(session, inn, name="Org", **kw):
    org = Organization(inn=inn, name_1c=name, **kw)
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


# --- mrr_fact -------------------------------------------------------------


def test_mrr_fact_lists_contributors_with_amounts(db_session: Session):
    a = _org(db_session, "10", name="A", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("10000"))
    b = _org(db_session, "11", name="B", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("5000"))
    ch_a = _charge(db_session, a, 2026, 4, 10000)
    ch_b = _charge(db_session, b, 2026, 4, 5000)
    _pay(db_session, a, ch_a, 10000, date(2026, 4, 5))
    _pay(db_session, b, ch_b, 5000, date(2026, 4, 7))
    # шум: платёж за другой месяц не должен попасть
    ch_a_other = _charge(db_session, a, 2026, 3, 10000)
    _pay(db_session, a, ch_a_other, 10000, date(2026, 3, 1))

    criteria = ReportCriteria(metric="mrr_fact", period="2026-04")
    rows = build_composition_report(db_session, criteria)
    names = sorted(r["name"] for r in rows)
    assert names == ["A", "B"]
    assert all(r["contribution"] in (10000.0, 5000.0) for r in rows)
    assert control_value_for("mrr_fact", rows) == 15000.0


def test_mrr_fact_excludes_excluded_from_analytics(db_session: Session):
    a = _org(db_session, "20", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("10000"))
    b = _org(db_session, "21", status=OrgStatus.ACTIVE,
             monthly_ap=Decimal("5000"), excluded_from_analytics=True)
    ch_a = _charge(db_session, a, 2026, 4, 10000)
    ch_b = _charge(db_session, b, 2026, 4, 5000)
    _pay(db_session, a, ch_a, 10000, date(2026, 4, 5))
    _pay(db_session, b, ch_b, 5000, date(2026, 4, 7))

    criteria = ReportCriteria(metric="mrr_fact", period="2026-04")
    rows = build_composition_report(db_session, criteria)
    assert {r["inn"] for r in rows} == {"20"}


def test_mrr_fact_empty_for_invalid_period(db_session: Session):
    criteria = ReportCriteria(metric="mrr_fact", period="not-a-date")
    assert build_composition_report(db_session, criteria) == []


# --- mrr_plan -------------------------------------------------------------


def test_mrr_plan_lists_active_subscribers(db_session: Session):
    _org(db_session, "30", name="A", status=OrgStatus.ACTIVE,
         monthly_ap=Decimal("10000"))
    _org(db_session, "31", name="B", status=OrgStatus.ACTIVE,
         monthly_ap=Decimal("5000"))
    _org(db_session, "32", name="C-churn", status=OrgStatus.CHURNED,
         monthly_ap=Decimal("999"))  # неактивен — не считаем
    _org(db_session, "33", name="D-noap", status=OrgStatus.ACTIVE,
         monthly_ap=None)  # без АП — не считаем

    criteria = ReportCriteria(metric="mrr_plan")
    rows = build_composition_report(db_session, criteria)
    assert {r["name"] for r in rows} == {"A", "B"}
    assert control_value_for("mrr_plan", rows) == 15000.0

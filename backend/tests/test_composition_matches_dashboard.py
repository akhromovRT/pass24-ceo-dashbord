"""Инвариант: control_value в composition совпадает с плиткой Dashboard.

Регрессионный контракт — если этот файл зелёный, дашборд и drill-down
показывают одни и те же цифры."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    AllocationBasis, ChargeSource, Contract, ContractType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation, User, UserRole,
)


@pytest.fixture
def client(db_session: Session):
    def _sess():
        yield db_session

    def _user():
        return User(name="T", email="t@t.ru", hashed_password="x",
                    role=UserRole.ADMIN, is_active=True)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _org(s, inn, name="O", **kw):
    org = Organization(inn=inn, name_1c=name, **kw)
    s.add(org); s.commit(); s.refresh(org)
    return org


def _charge(s, org, y, m, amount):
    c = MonthlyCharge(organization_id=org.id, year=y, month=m,
                     amount=Decimal(str(amount)),
                     source=ChargeSource.SYNTHETIC_TARIFF)
    s.add(c); s.commit(); s.refresh(c)
    return c


def _pay(s, org, charge, amount, pay_date):
    contract = Contract(organization_id=org.id,
                       contract_type=ContractType.SUBSCRIPTION)
    s.add(contract); s.commit(); s.refresh(contract)
    doc = Document(contract_id=contract.id, organization_id=org.id,
                  doc_type=DocType.PAYMENT, doc_date=pay_date,
                  amount=Decimal(str(amount)))
    s.add(doc); s.commit(); s.refresh(doc)
    alloc = PaymentAllocation(payment_document_id=doc.id,
                             monthly_charge_id=charge.id,
                             allocated_amount=Decimal(str(amount)),
                             basis=AllocationBasis.EXPLICIT_PERIOD)
    s.add(alloc); s.commit()


@pytest.fixture
def populated(db_session: Session):
    """Реалистичная сеть: 5 клиентов, начисления и аллокации за 4 месяца."""
    today = date.today()
    months = []
    for i in range(4):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    orgs = []
    for i, plan in enumerate([10000, 8000, 6000, 4000, 2000], start=1):
        o = _org(db_session, f"INV{i:03d}", name=f"O{i}",
                 status=OrgStatus.ACTIVE, monthly_ap=Decimal(str(plan)))
        orgs.append(o)

    for org in orgs:
        plan = float(org.monthly_ap)
        for (y, m) in months:
            ch = _charge(db_session, org, y, m, plan)
            _pay(db_session, org, ch, plan * 0.8, date(y, m, 5))

    # один отток — последний платёж 70 дней назад
    o_stop = _org(db_session, "INV900", name="Stopped",
                  status=OrgStatus.ACTIVE)
    long_ago = today - timedelta(days=70)
    if long_ago.year == today.year:
        ch_stop = _charge(db_session, o_stop, long_ago.year, long_ago.month, 100)
        _pay(db_session, o_stop, ch_stop, 100, long_ago)

    return {"orgs": orgs, "months": months, "today": today}


def _summary(client) -> dict:
    return client.get("/api/v1/dashboard/summary").json()


def _control(client, metric: str, period: str | None = None):
    payload = {"metric": metric}
    if period is not None:
        payload["period"] = period
    return client.post("/api/v1/reports/composition/preview",
                        json=payload).json()["control_value"]


def test_inv_mrr_fact(client, populated):
    s = _summary(client)
    control = _control(client, "mrr_fact", s["fact_month"])
    assert abs(s["mrr_fact"] - control) < 0.01


def test_inv_mrr_plan(client, populated):
    s = _summary(client)
    control = _control(client, "mrr_plan")
    assert abs(s["mrr_plan"] - control) < 0.01


def test_inv_collected_current(client, populated):
    s = _summary(client)
    control = _control(client, "collected_current", s["current_month_label"])
    assert abs(s["current_month_collected"] - control) < 0.01


def test_inv_active_clients(client, populated):
    s = _summary(client)
    control = _control(client, "active_clients")
    assert s["active_clients"] == control


def test_inv_new_paid_curr_year(client, populated):
    s = _summary(client)
    control = _control(client, "new_paid_curr_year")
    assert s["new_paid_curr_year"] == control


def test_inv_new_paid_prev_month(client, populated):
    s = _summary(client)
    control = _control(client, "new_paid_prev_month")
    assert s["new_paid_prev_month"] == control


def test_inv_new_paid_curr_month(client, populated):
    s = _summary(client)
    control = _control(client, "new_paid_curr_month")
    assert s["new_paid_curr_month"] == control


def test_inv_stopped_since_year_start(client, populated):
    s = _summary(client)
    control = _control(client, "stopped_since_year_start")
    assert s["stopped_since_year_start"] == control

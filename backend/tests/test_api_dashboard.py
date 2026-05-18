from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    AllocationBasis,
    ChargeSource,
    Contract,
    Document,
    DocType,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
    User,
    UserRole,
)


@pytest.fixture
def client(db_session: Session):
    def override_get_session():
        yield db_session

    def override_get_current_user():
        return User(name="T", email="t@t.ru", hashed_password="x",
                    role=UserRole.ADMIN, is_active=True)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_ledger_org(db_session: Session) -> Organization:
    """Орг с начислением 01/2026 (10000) и платежом 8000, разнесённым на него."""
    org = Organization(inn="7700000001", name_1c="Орг", status=OrgStatus.ACTIVE,
                        monthly_ap=Decimal("10000"))
    db_session.add(org)
    db_session.flush()
    contract = Contract(organization_id=org.id, contract_number="1C-PAYMENTS",
                        raw_name="payments")
    db_session.add(contract)
    db_session.flush()
    charge = MonthlyCharge(organization_id=org.id, year=2026, month=1,
                           amount=Decimal("10000"),
                           source=ChargeSource.SYNTHETIC_TARIFF)
    db_session.add(charge)
    db_session.flush()
    pay = Document(contract_id=contract.id, organization_id=org.id,
                   doc_type=DocType.PAYMENT, amount=Decimal("8000"),
                   doc_date=date(2026, 1, 20), raw_name="оплата")
    db_session.add(pay)
    db_session.flush()
    db_session.add(PaymentAllocation(
        payment_document_id=pay.id, monthly_charge_id=charge.id,
        allocated_amount=Decimal("8000"), basis=AllocationBasis.FIFO))
    db_session.commit()
    return org


def test_collection_trend_uses_ledger(client, db_session: Session):
    _make_ledger_org(db_session)
    resp = client.get("/api/v1/dashboard/collection-trend")
    assert resp.status_code == 200
    rows = resp.json()
    jan = next(r for r in rows if r["label"] == "01/2026")
    assert jan["accrued"] == 10000.0
    assert jan["collected"] == 8000.0
    assert jan["ratio"] == 80.0
    assert "is_current_month" in jan


def test_collection_trend_empty(client):
    resp = client.get("/api/v1/dashboard/collection-trend")
    assert resp.status_code == 200
    assert resp.json() == []


def test_cash_inflow_structure(client, db_session: Session):
    _make_ledger_org(db_session)
    resp = client.get("/api/v1/dashboard/cash-inflow")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows
    for key in ("year", "month", "current", "advance", "arrears",
                "undetermined", "non_subscription"):
        assert key in rows[0]


def test_aging_from_ledger(client, db_session: Session):
    _make_ledger_org(db_session)  # начислено 10000, разнесено 8000 → остаток 2000
    resp = client.get("/api/v1/dashboard/aging")
    assert resp.status_code == 200
    rows = resp.json()
    assert sum(r["amount"] for r in rows) == pytest.approx(2000.0)


def test_summary_has_current_month_fields(client, db_session: Session):
    _make_ledger_org(db_session)
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("current_month_label", "current_month_collected",
                "days_passed", "days_in_month",
                "debt_90plus_amount", "debt_90plus_share",
                "collection_rate_fact"):
        assert key in body
    assert 1 <= body["days_in_month"] <= 31


def test_attention_aggregates_open_alerts(client, db_session: Session):
    org = Organization(inn="7700000002", name_1c="О2", status=OrgStatus.ACTIVE)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    db_session.add(Alert(
        organization_id=org.id, alert_type=AlertType.LARGE_DEBT,
        severity=AlertSeverity.CRITICAL, title="Долг", status=AlertStatus.OPEN,
        metric_value=500000.0))
    db_session.add(Alert(
        organization_id=org.id, alert_type=AlertType.LARGE_DEBT,
        severity=AlertSeverity.CRITICAL, title="Долг2", status=AlertStatus.OPEN,
        metric_value=300000.0))
    db_session.add(Alert(
        organization_id=org.id, alert_type=AlertType.NEW_CLIENT,
        severity=AlertSeverity.INFO, title="Новый", status=AlertStatus.RESOLVED))
    db_session.commit()
    resp = client.get("/api/v1/dashboard/attention")
    assert resp.status_code == 200
    rows = resp.json()
    debt = next(r for r in rows if r["type"] == "large_debt")
    assert debt["count"] == 2
    assert debt["amount"] == 800000.0
    assert all(r["type"] != "new_client" for r in rows)

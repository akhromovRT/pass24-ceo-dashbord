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
    Contract,
    Document,
    DocType,
    Organization,
    OrgStatus,
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


@pytest.fixture
def org_with_payments(db_session: Session) -> Organization:
    org = Organization(inn="7700000001", name_1c="Орг",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"))
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    contract = Contract(organization_id=org.id, raw_name="Д")
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    for d, amt in [(date(2026, 1, 15), 10000), (date(2026, 3, 10), 8000)]:
        db_session.add(Document(
            contract_id=contract.id, organization_id=org.id,
            doc_type=DocType.PAYMENT, amount=Decimal(amt), doc_date=d,
        ))
    db_session.commit()
    return org


def test_collection_trend_only_months_with_data(client, org_with_payments):
    resp = client.get("/api/v1/dashboard/collection-trend")
    assert resp.status_code == 200
    rows = resp.json()
    labels = {r["label"] for r in rows}
    assert labels == {"01/2026", "03/2026"}


def test_collection_trend_empty(client):
    resp = client.get("/api/v1/dashboard/collection-trend")
    assert resp.status_code == 200
    assert resp.json() == []


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


def test_summary_has_current_month_fields(client, org_with_payments):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("current_month_label", "current_month_collected",
                "days_passed", "days_in_month",
                "debt_90plus_amount", "debt_90plus_share",
                "collection_rate_fact"):
        assert key in body
    assert 1 <= body["days_in_month"] <= 31

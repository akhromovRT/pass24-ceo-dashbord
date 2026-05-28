"""Тесты на авто-заполнение churn_month при PATCH /organizations/{inn}."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    Contract,
    ContractType,
    DocType,
    Document,
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
        return User(
            name="Test",
            email="t@e",
            hashed_password="x",
            role=UserRole.ADMIN,
            is_active=True,
        )

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _org_with_payment(db_session: Session, last_payment_date: date | None) -> Organization:
    org = Organization(
        inn="7700001234",
        name_1c="Тест",
        status=OrgStatus.ACTIVE,
        monthly_ap=Decimal("10000"),
    )
    db_session.add(org)
    db_session.flush()
    if last_payment_date is not None:
        contract = Contract(
            organization_id=org.id,
            contract_type=ContractType.SUBSCRIPTION,
            raw_name="Договор",
        )
        db_session.add(contract)
        db_session.flush()
        db_session.add(
            Document(
                contract_id=contract.id,
                organization_id=org.id,
                doc_type=DocType.PAYMENT,
                doc_date=last_payment_date,
                amount=Decimal("10000"),
                raw_name="Оплата",
            )
        )
    db_session.commit()
    return org


def test_active_to_churned_autosets_churn_month_from_last_payment(
    client: TestClient,
    db_session: Session,
):
    _org_with_payment(db_session, last_payment_date=date(2025, 6, 15))
    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"status": "churned"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "churned"
    assert (
        body["churn_month"] == "2025-06-01"
    ), "churn_month должен быть первым числом месяца последнего платежа"


def test_active_to_churned_with_explicit_churn_month_uses_it(
    client: TestClient,
    db_session: Session,
):
    _org_with_payment(db_session, last_payment_date=date(2025, 6, 15))
    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"status": "churned", "churn_month": "2025-04-15"},
    )
    assert resp.status_code == 200
    assert (
        resp.json()["churn_month"] == "2025-04-01"
    ), "Pydantic-валидатор должен нормализовать день к 1-му числу"


def test_churned_without_payments_returns_400(
    client: TestClient,
    db_session: Session,
):
    _org_with_payment(db_session, last_payment_date=None)
    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"status": "churned"},
    )
    assert resp.status_code == 400
    assert "вручную" in resp.json()["detail"]


def test_churned_to_active_clears_churn_month(
    client: TestClient,
    db_session: Session,
):
    org = _org_with_payment(db_session, last_payment_date=date(2025, 6, 15))
    org.status = OrgStatus.CHURNED
    org.churn_month = date(2025, 6, 1)
    db_session.add(org)
    db_session.commit()

    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["churn_month"] is None


def test_patch_unrelated_field_does_not_clear_churn_month(
    client: TestClient,
    db_session: Session,
):
    """Защита: правка name_display у CHURNED-клиента НЕ должна задеть churn_month."""
    org = _org_with_payment(db_session, last_payment_date=date(2025, 6, 15))
    org.status = OrgStatus.CHURNED
    org.churn_month = date(2025, 6, 1)
    db_session.add(org)
    db_session.commit()

    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"name_display": "Новое имя"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name_display"] == "Новое имя"
    assert body["churn_month"] == "2025-06-01"


# --- TRANSIT — поведение зеркальное CHURNED ---------------------------------


def test_active_to_transit_autosets_churn_month_from_last_payment(
    client: TestClient,
    db_session: Session,
):
    """TRANSIT — это юр.лицо, переставшее платить за себя (переоформление
    ИНН или транзитный плательщик). churn_month заполняется автоматически
    так же как для CHURNED — это месяц последнего платежа."""
    _org_with_payment(db_session, last_payment_date=date(2025, 8, 20))
    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"status": "transit"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "transit"
    assert body["churn_month"] == "2025-08-01"


def test_transit_to_active_clears_churn_month(
    client: TestClient,
    db_session: Session,
):
    """Откат из TRANSIT в ACTIVE сбрасывает churn_month — клиент снова платит."""
    org = _org_with_payment(db_session, last_payment_date=date(2025, 6, 15))
    org.status = OrgStatus.TRANSIT
    org.churn_month = date(2025, 6, 1)
    db_session.add(org)
    db_session.commit()

    resp = client.patch(
        "/api/v1/organizations/7700001234",
        json={"status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["churn_month"] is None

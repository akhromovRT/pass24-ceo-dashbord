from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
    ChargeSource,
    ClientObject,
    MonthlyCharge,
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


def test_segments_counts(client, db_session: Session):
    org = Organization(inn="7700000010", name_1c="Платит",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        in_registry=True, total_debt=Decimal("50000"))
    db_session.add(org)
    db_session.commit()
    resp = client.get("/api/v1/billing/segments")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("total", "mrr_plan", "paying", "partial",
                "not_paying", "debtors"):
        assert key in body
    assert body["total"] == 1
    assert body["debtors"] == 1
    # Без записей в client_objects fallback на objects_count_declared|1.
    assert body["objects_total"] == 1


def test_segments_objects_total_counts_client_objects(
    client, db_session: Session,
):
    org1 = Organization(inn="7700000011", name_1c="С тремя объектами",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        in_registry=True)
    org2 = Organization(inn="7700000012", name_1c="С заявленными 5",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        in_registry=True, objects_count_declared=5)
    org3 = Organization(inn="7700000013", name_1c="Без объектов",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        in_registry=True)
    db_session.add_all([org1, org2, org3])
    db_session.commit()
    # У org1 — три записи в client_objects
    for i in range(3):
        db_session.add(ClientObject(
            organization_id=org1.id, name=f"Объект {i+1}",
        ))
    db_session.commit()

    body = client.get("/api/v1/billing/segments").json()
    # org1: 3 (по факту), org2: 5 (declared), org3: 1 (fallback)
    assert body["objects_total"] == 3 + 5 + 1


def test_debtors_have_aging_fields(client, db_session: Session):
    org = Organization(inn="7700000020", name_1c="Должник",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        total_debt=Decimal("45000"))
    db_session.add(org)
    db_session.commit()
    resp = client.get("/api/v1/billing/debtors")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert "months_overdue" in row
    assert "aging_bucket" in row
    assert row["aging_bucket"] == "90+"


def test_debtors_aging_uses_calendar_months(client, db_session: Session):
    """Возраст долга в /debtors — по календарным месяцам неоплаты, а не долг/АП.
    Согласовано с дашбордом и модулем отчётов через services/aging.py."""
    today = date.today()
    # долг/АП = 5 → старая логика дала бы 90+; неоплаченное начисление
    # текущего месяца → календарный возраст 0 → корзина 0-30
    org = Organization(inn="7700000030", name_1c="Свежий долг",
                        status=OrgStatus.ACTIVE, monthly_ap=Decimal("10000"),
                        total_debt=Decimal("50000"))
    db_session.add(org)
    db_session.flush()
    db_session.add(MonthlyCharge(
        organization_id=org.id, year=today.year, month=today.month,
        amount=Decimal("50000"), source=ChargeSource.SYNTHETIC_TARIFF))
    db_session.commit()
    rows = client.get("/api/v1/billing/debtors").json()
    row = next(r for r in rows if r["inn"] == "7700000030")
    assert row["aging_bucket"] == "0-30"
    assert row["months_overdue"] == 0

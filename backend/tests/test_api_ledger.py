from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import (
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


def _ledger_org(db_session: Session, inn="7710000001"):
    """Орг с начислениями 01/2026 и 02/2026, платёж 10000 разнесён на январь."""
    org = Organization(inn=inn, name_1c="Орг", status=OrgStatus.ACTIVE,
                        monthly_ap=Decimal("10000"))
    db_session.add(org)
    db_session.flush()
    contract = Contract(organization_id=org.id, contract_number="1C-PAYMENTS",
                        raw_name="payments")
    db_session.add(contract)
    db_session.flush()
    c1 = MonthlyCharge(organization_id=org.id, year=2026, month=1,
                       amount=Decimal("10000"), source=ChargeSource.SYNTHETIC_TARIFF)
    c2 = MonthlyCharge(organization_id=org.id, year=2026, month=2,
                       amount=Decimal("10000"), source=ChargeSource.SYNTHETIC_TARIFF)
    db_session.add(c1)
    db_session.add(c2)
    db_session.flush()
    pay = Document(contract_id=contract.id, organization_id=org.id,
                   doc_type=DocType.PAYMENT, amount=Decimal("10000"),
                   doc_date=date(2026, 1, 20), raw_name="оплата")
    db_session.add(pay)
    db_session.flush()
    db_session.add(PaymentAllocation(
        payment_document_id=pay.id, monthly_charge_id=c1.id,
        allocated_amount=Decimal("10000"), basis=AllocationBasis.FIFO))
    db_session.commit()
    return org, pay


def test_org_ledger_endpoint(client, db_session: Session):
    org, _ = _ledger_org(db_session)
    resp = client.get(f"/api/v1/organizations/{org.inn}/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert "months" in body and "payments" in body
    assert len(body["months"]) == 2
    jan = next(m for m in body["months"] if m["month"] == 1)
    assert jan["accrued"] == 10000.0
    assert jan["allocated"] == 10000.0
    assert jan["status"] == "paid"
    assert len(body["payments"]) == 1


def test_tariff_history_get_and_post(client, db_session: Session):
    org, _ = _ledger_org(db_session)
    resp = client.get(f"/api/v1/organizations/{org.inn}/tariffs")
    assert resp.status_code == 200
    assert resp.json() == []
    new = client.post(f"/api/v1/organizations/{org.inn}/tariffs",
                       json={"valid_from": "2026-06-01", "monthly_amount": 15000})
    assert new.status_code == 200
    after = client.get(f"/api/v1/organizations/{org.inn}/tariffs").json()
    assert any(t["monthly_amount"] == 15000.0 for t in after)


def test_manual_allocation_override(client, db_session: Session):
    org, pay = _ledger_org(db_session)
    resp = client.put(
        f"/api/v1/payments/{pay.id}/allocations",
        json={"allocations": [
            {"year": 2026, "month": 1, "amount": 6000},
            {"year": 2026, "month": 2, "amount": 4000},
        ]},
    )
    assert resp.status_code == 200
    rows = db_session.exec(
        select(PaymentAllocation).where(
            PaymentAllocation.payment_document_id == pay.id)
    ).all()
    assert len(rows) == 2
    assert all(r.is_manual for r in rows)

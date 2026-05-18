import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AllocationBasis,
    ChargeSource,
    MonthlyCharge,
    PaymentAllocation,
    TariffPeriod,
)


def test_tariff_period_persists(db_session):
    org_id = uuid.uuid4()
    tp = TariffPeriod(
        organization_id=org_id,
        valid_from=date(2025, 1, 1),
        monthly_amount=Decimal("12100.00"),
    )
    db_session.add(tp)
    db_session.commit()
    db_session.refresh(tp)
    assert tp.id is not None
    assert tp.monthly_amount == Decimal("12100.00")
    assert tp.created_by is None


def test_monthly_charge_unique_period(db_session):
    org_id = uuid.uuid4()
    c1 = MonthlyCharge(
        organization_id=org_id, year=2026, month=3,
        amount=Decimal("12100.00"), source=ChargeSource.SYNTHETIC_TARIFF,
    )
    db_session.add(c1)
    db_session.commit()
    c2 = MonthlyCharge(
        organization_id=org_id, year=2026, month=3,
        amount=Decimal("12100.00"), source=ChargeSource.SYNTHETIC_TARIFF,
    )
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_payment_allocation_persists(db_session):
    alloc = PaymentAllocation(
        payment_document_id=uuid.uuid4(),
        monthly_charge_id=None,
        allocated_amount=Decimal("5000.00"),
        basis=AllocationBasis.FIFO,
    )
    db_session.add(alloc)
    db_session.commit()
    db_session.refresh(alloc)
    assert alloc.is_manual is False
    assert alloc.basis == AllocationBasis.FIFO
